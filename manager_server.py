import json
import signal
from multiprocessing import Process

import flask
import sys
from flask import request, jsonify, Response
import os
import os.path as ospath

manager_server = flask.Flask(__name__)
manager_server.config["DEBUG"] = True

""" config information dictionary mapped to 
    config information file name on disk 
    caching on memory for faster access
"""
config_infor_dict = {}

instances_list = []

""" Current project working directory for hierarchically 
    declaring paths and folders for files and basefs 
"""
proj_work_dir = ospath.dirname(ospath.realpath(__file__))

""" Directory for container instances that mounts containers and 
    its instances 
"""
cont_inst_dir = ospath.join(proj_work_dir, 'container')

"""Dictionary of container processes 
"""
container_dict = {}


@manager_server.route('/config', methods=['POST'])
def create_config():
    content = request.get_json()
    if content is None:
        return Response(status=409)
    filename = content["name"]
    major_version = content["major"]
    minor_version = content["minor"]

    if filename is None or major_version is None or minor_version is None:
        return Response(status=409)
    global config_infor_dict
    config_file_name = filename + "-" + major_version + "-" + minor_version + ".cfg"
    config_infor_dict[config_file_name] = content
    f = open(config_file_name, "w")
    f.write(content)
    f.close()
    return Response(status=200)


@manager_server.route('/cfginfo', methods=['GET'])
def get_config_info():
    result_list = []
    for each_config_infor in config_infor_dict.keys():
        result_list.append(each_config_infor)
    output_dict = {"files": result_list}
    response = jsonify(output_dict)
    response.status_code = 200
    return response


def do_mount(baseimg_dir, mount_point):
    filename = mount_point.split(" ")[0]
    file_folder = filename.split(".")[0]
    folder = mount_point.split(" ")[1]
    if folder[0] == '/':
        folder = folder[1:]
    permission = mount_point.split(" ")[2]
    mount_dir = ospath.join(proj_work_dir, "mountables")
    filepath = ospath.join(mount_dir, filename)
    file_folder = ospath.join(mount_dir, file_folder)
    folder_path = ospath.join(baseimg_dir, folder)
    if not ospath.exists(folder_path):
        os.system('sudo mkdir {}'.format(folder_path))
    if not ospath.exists(file_folder):
        os.system('tar -xf {} -C {}'.format(filepath, mount_dir))
    if permission == "READ":
        os.system('sudo mount --bind -o ro {} {}'.format(file_folder, folder_path))
    else:
        os.system('sudo mount --bind -o rw {} {}'.format(file_folder, folder_path))


def start_container(instance_base_image_dir, config_information):
    startup_env = config_information['startup_env']
    if startup_env[-1] != ';':
        startup_env = startup_env + ';'
    os.system('unshare -p -f --mount-proc={} chroot {} /bin/bash -c "export {} {}"'.format(ospath.join(instance_base_image_dir, 'proc'),
                                                                                           instance_base_image_dir, startup_env,
                                                                                           config_information[
                                                                                               'startup_script']))


@manager_server.route('/launch', methods=['POST'])
def launch_inst():
    content = request.get_json()
    if content is None:
        return Response(status=409)
    
    config_name = content["name"]
    major_version = content["major"]
    minor_version = content["minor"]
    if config_name is None or major_version is None or minor_version is None:
        return Response(status=409)
    global instances_list

    instance_name = "instance_" + config_name
    instances_list.append(instance_name)

    inst_dir = ospath.join(cont_inst_dir, instance_name)
    if not ospath.exists(inst_dir):
        os.makedirs(inst_dir, 777)
    
    os.system("tar -zxf base_images/basefs.tar.gz -C " + inst_dir + "")
    instance_base_image_dir = ospath.join(inst_dir, 'basefs')
    
    config_information = config_infor_dict[config_name+"-"+major_version+"-"+minor_version+".cfg"]
    
    for each_mount_point in config_information['mounts']:
        do_mount(instance_base_image_dir, each_mount_point)

    os.system('mount -t proc proc {}'.format(ospath.join(instance_base_image_dir, 'proc')))
    container_process = Process(target=start_container, args=(instance_base_image_dir, config_information))
    container_dict[instance_name] = container_process
    container_process.start()
    # Set group id
    os.setpgid(container_process.pid, container_process.pid)

    for config_file in config_infor_dict.keys():
        if config_file == config_name:
            # Code for launching instance of a specific container given
            # config_name, major_version and minor_version to be written here

            instance_name = "instance_" + config_name
            instances_list.append(instance_name)
            output_dict = {}
            output_dict["instance"] = instance_name
            output_dict["name"] = config_name
            output_dict["major"] = major_version
            output_dict["minor"] = minor_version
            response = jsonify(output_dict)
            response.status_code = 200
            return response 
    return Response(status=404)

    
@manager_server.route('/list', methods=['GET'])
def get_inst_list():
    output_dict = {"instances": instances_list}
    response = jsonify(output_dict)
    response.status_code = 200
    return response


def teardown_container(one_instance):
    image_dir = ospath.join(cont_inst_dir, one_instance, 'basefs')
    instance_info = instances_list.pop(one_instance)
    container_process = container_dict.pop(one_instance)
    # kill the whole group of container process
    os.killpg(container_process.pid, signal.SIGKILL)

    with open(ospath.join(proj_work_dir, '{}-{}-{}.cfg'.format(instance_info['name'],
                                                         instance_info['major'],
                                                         instance_info['minor']))) as fp:
        config_obj = json.load(fp)
    # umount all mounted files
    mount_paths = [mount_config.split(' ')[1] for mount_config in config_obj['mounts']]
    mount_paths.sort()
    mount_paths.reverse()
    for mount_path in mount_paths:
        if mount_path[0] == '/':
            mount_path = mount_path[1:]
        mount_path = ospath.join(image_dir, mount_path)
        os.system('umount -l {}'.format(mount_path))
    # umount proc
    os.system('chroot {} /bin/bash -c "umount proc"'.format(image_dir))
    # remove container directory
    os.system('rm -rf {}'.format(ospath.join(cont_inst_dir, one_instance)))


@manager_server.route('/destroy/<path:text>', methods=['DELETE'])
def del_inst(text):
    global instances_list
    if text is None:
        return Response(status=409)
    for one_instance in instances_list:
        if one_instance == text:
            teardown_container(one_instance)

            instances_list.remove(one_instance)
            return Response(status=200)
    return Response(status=404)


@manager_server.route('/destroyall', methods=['DELETE'])
def del_all_inst():
    global instances_list

    
    instances_list.clear()
    return Response(status=200)


if __name__ == '__main__':
    # manager_server.run(host="localhost", port=int(sys.argv[2]))
    manager_server.run(host="localhost", port=8080)
