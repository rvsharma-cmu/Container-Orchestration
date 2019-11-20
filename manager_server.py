import flask
import sys
from flask import request, jsonify, Response
import os

manager_server = flask.Flask(__name__)
manager_server.config["DEBUG"] = True

config_infor_list = []
instances_list = []


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
    global config_infor_list
    config_file_name = filename + "-" + major_version + "-" + minor_version + ".cfg"
    config_infor_list.append(config_file_name)
    f = open(config_file_name, "w")
    f.write(content)
    f.close()
    return Response(status=200)


@manager_server.route('/cfginfo', methods=['GET'])
def get_config_info():
    output_dict = {"files": config_infor_list}
    response = jsonify(output_dict)
    response.status_code = 200
    return response


@manager_server.route('/launch', methods=['POST'])
def launch_inst():
    content = request.get_json()
    if content is None:
        return Response(status=409)
    
    inst_name = content["name"]
    inst_major = content["major"]
    inst_minor = content["minor"]
    if inst_name is None or inst_major is None or inst_minor is None:
        return Response(status=409)
    global instances_list
    for config_file in config_infor_list:
        if config_file == inst_name:
            # Code for launching instance of a specific container given
            # inst_name, inst_major and inst_minor to be written here

            
            instance_name = "instance_" + inst_name
            instances_list.append(instance_name)
            output_dict = {}
            output_dict["instance"] = instance_name
            output_dict["name"] = inst_name
            output_dict["major"] = inst_major
            output_dict["minor"] = inst_minor
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


@manager_server.route('/destroy/<path:text>', methods=['DELETE'])
def del_inst(text):
    global instances_list
    if text is None:
        return Response(status=409)
    for one_instance in instances_list:
        if one_instance == text:
            # Code to stop instance to be written here

            instances_list.remove(one_instance)
            return Response(status=200)
    return Response(status=404)


@manager_server.route('/destroyall', methods=['DELETE'])
def del_all_inst():
    global instances_list
    for one_instance in instances_list:
        # Code to kill instance to be written here

    
    instances_list.clear()
    return Response(status=200)


if __name__ == '__main__':
    # manager_server.run(host="localhost", port=int(sys.argv[2]))
    manager_server.run(host="localhost", port=8080
