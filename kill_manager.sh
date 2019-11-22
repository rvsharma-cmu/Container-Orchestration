ps -ef | grep manager_server | grep -v grep | awk '{print $2}' | xargs kill
