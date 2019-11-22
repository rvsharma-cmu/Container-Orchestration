import json
import signal
from multiprocessing import Process

import flask
import sys
from flask import request, jsonify, Response
from collections import OrderedDict
import os
import os.path as ospath
import pdb
import copy
import time
import psutil

manager_server = flask.Flask(__name__)
manager_server.config["DEBUG"] = True

""" config information dictionary mapped to 
    config information file name on disk 
    caching on memory for faster access
"""
config_infor_dict = OrderedDict()

PROCNAME = "tiny.sh"

server_awake = False


""" 
    Current project working directory for hierarchically 
    declaring paths and folders for files and basefs 
"""
proj_work_dir = ospath.dirname(ospath.realpath(__file__))

""" 
    Directory for container instances that mounts containers and 
    its instances 
"""
cont_inst_dir = ospath.join(proj_work_dir, 'container')

"""
    Dictionary of container processes 
"""
container_dict = {}

"""
    Config instance dictionary 
"""
config_instance_dict = OrderedDict()

"""
    Instances list of dictionaries. Updated while 
    launching and destroying container instances 
"""
instances_list_dict = {}


@manager_server.route('/config', methods=['POST'])
def create_config():
    global server_awake
    if not server_awake:
        time.sleep(3)
        server_awake = True
    content = request.get_json()
    if content is None:
        return Response(status=409)

    for each_attr in ["name", "major", "minor"]:
        if each_attr not in content:
            return Response(status=409)

    filename = content["name"]
    major_version = content["major"]
    minor_version = content["minor"]

    if filename is None or major_version is None or minor_version is None:
        return Response(status=409)
    global config_infor_dict
    config_file_name = filename + "-" + major_version + "-" + minor_version + ".cfg"
    if config_file_name in config_infor_dict.keys():
        return Response(status=409)
    config_infor_dict[config_file_name] = content
    f = open(config_file_name, "w")
    f.write(json.dumps(content))
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
    os.system('sudo unshare -p -f --mount-proc={} chroot {} /bin/bash -c "export {} {}"'.format(ospath.join(instance_base_image_dir, 'proc'),
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
    global instances_list_dict
    
    instance_name = "instance_" + config_name + "_" + major_version + "_" + minor_version
    if not ospath.exists(cont_inst_dir):
        os.makedirs(cont_inst_dir, mode=0o777)
    inst_dir = ospath.join(cont_inst_dir, instance_name)
    if not ospath.exists(inst_dir):
        os.makedirs(inst_dir, mode=0o777)
    
    os.system("tar -zxf base_images/basefs.tar.gz -C " + inst_dir + "")
    instance_base_image_dir = ospath.join(inst_dir, 'basefs')
    config_file_name = config_name+"-"+major_version+"-"+minor_version+".cfg"
    config_information = config_infor_dict[config_file_name]
    
    for each_mount_point in config_information['mounts']:
        do_mount(instance_base_image_dir, each_mount_point)
    os.system('sudo mount -t proc proc {}'.format(ospath.join(instance_base_image_dir, 'proc')))
    container_process = Process(target=start_container, args=(instance_base_image_dir, config_information))
    container_dict[instance_name] = container_process
    container_process.start()
    os.setpgid(container_process.pid, container_process.pid)

    for config_file in config_infor_dict.keys():
        if config_file == config_file_name:
            # Code for launching instance of a specific container given
            # config_name, major_version and minor_version to be written here
            instance_name = "instance_" + config_name
            output_dict = {}

            output_dict["instance"] = instance_name
            output_dict["name"] = config_name
            output_dict["major"] = major_version
            output_dict["minor"] = minor_version
            if len(instances_list_dict) == 0:
                instances_list_dict['instances'] = [output_dict]
            else:
                inst_list = instances_list_dict['instances']
                inst_list.append(output_dict)
                instances_list_dict['instances'] = inst_list
            response = jsonify(output_dict)
            response.status_code = 200
            time.sleep(3)
            return response 
    return Response(status=404)

    
@manager_server.route('/list', methods=['GET'])
def get_inst_list():
    if len(instances_list_dict) == 0:
        instances_list_dict['instances'] = []
    response = jsonify(instances_list_dict)
    response.status_code = 200
    return response


def destroy_container(one_instance):
    
    instance_directory = one_instance['instance']+"_"+one_instance['major']+"_"+one_instance['minor']
    image_dir = ospath.join(cont_inst_dir, instance_directory, 'basefs')
    container_process = container_dict[instance_directory]
    del container_dict[instance_directory]

    global instances_list_dict
    list_inst = instances_list_dict['instances']
    list_inst.remove(one_instance)
    instances_list_dict['instances'] = list_inst

    os.killpg(container_process.pid, signal.SIGKILL)

    config_name = one_instance['name']
    major_version = one_instance['major']
    minor_version = one_instance['minor']
    config_file_name = config_name+"-"+major_version+"-"+minor_version+".cfg"
    config_information = config_infor_dict[config_file_name]
    mount_paths = [mount_config.split(' ')[1] for mount_config in config_information['mounts']]
    mount_paths.sort()
    # umount in reverse order of mounting 
    mount_paths.reverse()
    for mount_path in mount_paths:
        if mount_path[0] == '/':
            mount_path = mount_path[1:]
        mount_path = ospath.join(image_dir, mount_path)
        os.system('sudo umount -l {}'.format(mount_path))
    os.system('sudo chroot {} /bin/bash -c "umount proc"'.format(image_dir))
    os.system('sudo rm -rf {}'.format(ospath.join(cont_inst_dir, instance_directory)))


@manager_server.route('/destroy/<path:text>', methods=['DELETE'])
def del_inst(text):
    deleted = False
    if text is None:
        return Response(status=409)
    for one_instance in instances_list_dict['instances']:
        if one_instance['instance'] == text:
            destroy_container(one_instance)
            deleted = True
    #not found
    if deleted:
        return Response(status=200)
    else:
        return Response(status=404)

    
def delete_all_dangling_proc():
    for proc in psutil.process_iter():
        if proc.name() == PROCNAME:
            try:
                process_id = proc.pid
                os.system('sudo kill -9 {}'.format(process_id))
            except psutil.NoSuchProcess as e:
                continue


@manager_server.route('/destroyall', methods=['DELETE'])
def del_all_inst():
    global instances_list_dict
    temp_instances_list_dict = copy.copy(list(instances_list_dict['instances']))
    for each_inst in temp_instances_list_dict:
        destroy_container(each_inst)
    delete_all_dangling_proc()
    return Response(status=200)


if __name__ == '__main__':
    
    manager_server.run(host="localhost", port=8080)
