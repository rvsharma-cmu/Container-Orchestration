download:
	mkdir -p base_images
	wget -P base_images/ http://www.andrew.cmu.edu/user/ayushagr/basefs.tar.gz

install:
	# Put any compilation instructions here if required
	# Any third party installations shuld also occur here
	sudo apt get pip3
	source venv/bin/activate
	pip3 install flask
	pip3 install psutil

manager:
	chmod 777 venv/bin/activate;sudo ./venv/bin/activate;python3 manager_server.py >> manager_server.log.txt 2>&1 &

clean:
	# Remove all config files stored by the manager in it's lifetime
	# and kill the manager process
	rm -rf *.cfg
	rm -rf *.html
	rm -rf *.html.*
	rm -rf manager_server_log.txt
	./kill_manager.sh


cli_tests: manager
	sleep 1
	./grading/cli_tests/test_1_upload.sh
	./grading/cli_tests/test_2_cfginfo.sh
	./grading/cli_tests/test_3_launch.sh
	./grading/cli_tests/test_4_list.sh
	./grading/cli_tests/test_5_destroyall.sh
	./kill_manager.sh

api_tests: manager
	sleep 1
	python3 grading/rest/grading.py
	clean
	./kill_manager.sh

	
	
