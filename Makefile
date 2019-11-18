
MANAGER_CMD=. venv/bin/activate;python3 manager_server.py
MANAGER_HOSTNAME=localhost
MANAGER_PORT=19190

download:
	mkdir -p base_images
	wget -P base_images/ http://www.andrew.cmu.edu/user/ayushagr/basefs.tar.gz

install:
	# Put any compilation instructions here if required
	# Any third party installations shuld also occur here

manager:
	$(MANAGER_CMD) $(MANAGER_HOSTNAME) $(MANAGER_PORT)

clean:
	# Remove all config files stored by the manager in it's lifetime
	# and kill the manager process

cli_tests: clean manager
	./grading/cli_tests/test_1_upload.sh
	./grading/cli_tests/test_2_cfginfo.sh
	./grading/cli_tests/test_3_launch.sh
	./grading/cli_tests/test_4_list.sh
	./grading/cli_tests/test_5_destroyall.sh

api_tests: clean manager
	python3 grading/rest/grading.py 

	
	
