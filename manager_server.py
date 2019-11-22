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
process_dictionary = {}

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
    mt_point_args = mount_point.split(" ")
    files = mt_point_args[0]
    folder_args = files.split(".")
    folder_create = folder_args[0]
    new_folder_name = mt_point_args[1]
    new_folder_name = truncate_path_name(new_folder_name)
    permission = mt_point_args[2]
    mount_dir = ospath.join(proj_work_dir, "mountables")
    path = ospath.join(mount_dir, files)
    folder_create = ospath.join(mount_dir, folder_create)
    base_image_path = ospath.join(baseimg_dir, new_folder_name)
    create_image_directory(base_image_path, folder_create, mount_dir, path)
    execute_mount_point(base_image_path, folder_create, permission)


def execute_mount_point(base_image_path, folder_create, permission):
    if permission == "READ":
        os.system('sudo mount --bind -o ro {} {}'.format(folder_create, base_image_path))
    else:
        os.system('sudo mount --bind -o rw {} {}'.format(folder_create, base_image_path))


def create_image_directory(base_image_path, folder_create, mount_dir, path):
    if not ospath.exists(base_image_path):
        os.system('sudo mkdir {}'.format(base_image_path))
    if not ospath.exists(folder_create):
        os.system('tar -xf {} -C {}'.format(path, mount_dir))


def truncate_path_name(folder):
    if folder[0] == '/':
        folder = folder[1:]
    return folder


def launch_container(instance_base_image_dir, config_information):
    startup_env = config_information['startup_env'] + ';'
    os.system('sudo unshare -p -f --mount-proc={} chroot {} /bin/bash -c "export {} {}"'
              .format(ospath.join(instance_base_image_dir, 'proc'), instance_base_image_dir,
                      startup_env, config_information['startup_script']))


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
    config_file_name = config_name + "-" + major_version + "-" + minor_version + ".cfg"
    config_information = config_infor_dict[config_file_name]

    initialize_container(config_information, instance_base_image_dir, instance_name)

    for config_file in config_infor_dict.keys():
        if config_file == config_file_name:
            # Code for launching instance of a specific container given
            # config_name, major_version and minor_version to be written here
            instance_name = "instance_" + config_name
            output_dict = {"instance": instance_name, "name": config_name, "major": major_version,
                           "minor": minor_version}

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


def initialize_container(config_information, instance_base_image_dir, instance_name):
    for each_mount_point in config_information['mounts']:
        do_mount(instance_base_image_dir, each_mount_point)
    os.system('sudo mount -t proc proc {}'.format(ospath.join(instance_base_image_dir, 'proc')))
    process = Process(target=launch_container, args=(instance_base_image_dir, config_information))
    process_dictionary[instance_name] = process
    process.start()
    os.setpgid(process.pid, process.pid)


@manager_server.route('/list', methods=['GET'])
def get_inst_list():
    if len(instances_list_dict) == 0:
        instances_list_dict['instances'] = []
    response = jsonify(instances_list_dict)
    response.status_code = 200
    return response


def destroy_container(one_instance):
    instance_directory = one_instance['instance'] + "_" + one_instance['major'] + "_" + one_instance['minor']
    image_dir = ospath.join(cont_inst_dir, instance_directory, 'basefs')
    process = process_dictionary[instance_directory]
    del process_dictionary[instance_directory]

    global instances_list_dict
    list_inst = instances_list_dict['instances']
    list_inst.remove(one_instance)
    instances_list_dict['instances'] = list_inst

    os.killpg(process.pid, signal.SIGKILL)

    config_name = one_instance['name']
    major_version = one_instance['major']
    minor_version = one_instance['minor']
    config_file_name = config_name + "-" + major_version + "-" + minor_version + ".cfg"
    config_information = config_infor_dict[config_file_name]
    mount_paths = []
    for mount_config in config_information['mounts']:
        mount_paths.append(mount_config.split(" ")[1])
    # umount in reverse order of mounting 
    (mount_paths.sort()).reverse()
    for mount_path in mount_paths:
        mount_path = truncate_path_name(mount_path)
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
    # not found
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
