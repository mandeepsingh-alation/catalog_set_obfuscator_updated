import subprocess
import os
import _pickle as pk
from string import Template
from pathlib import Path
from time import sleep
from config import *

# python-service
import logging
import time
from logging.handlers import SysLogHandler
from service import find_syslog, Service

class Obfuscator(Service):
    def __init__(self, *args, **kwargs):
        super(Obfuscator, self).__init__(*args, **kwargs)
        self.logger.addHandler(SysLogHandler(address=find_syslog(), facility=SysLogHandler.LOG_DAEMON))
        self.logger.setLevel(logging.INFO)
        # settings and setup
        # ensure data path exists
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
        # instantiate tagging database
        self.tag_db = tag_database()
        # load data or prepare for data save
        self.tag_db.db_check()

    # run the process
    def run(self):
        while not self.got_sigterm():
            # process catalog set data and get the current count of objects
            i = 0
            [i, cs_ids] = self.tag_db.catalog_set_process(i)

            # execute any changes
            if i > 0:
                # execute flag changes
                self.tag_db.execute_flag_change()
                # update data for cs_ids
                self.tag_db.update_data(tag_name=CS_TAG,new_data=cs_ids)

                # save the new database
                self.tag_db.db_save()

            time.sleep(SLEEP_TIME)

# end python-service

data_query_template = Template("""sudo chroot "/opt/alation/alation" /bin/su - alation -c "psql -p 5432 -U alation -h /tmp/ -d rosemeta -a -c '$query'" """)

select_aid_template = Template("""SELECT DISTINCT attribute_id FROM public.rosemeta_attribute_set_properties WHERE dynamicsetproperty_id IN ($cs_ids);""")

# create a function to execute bash commands
def bashCMD(command):

    """return the result bash command execution

    The *command* parameter is simply the bash command
    as a BYTESTRING."""

    # open a process
    process = subprocess.Popen('/bin/bash', stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # execute command and capture result
    response, err = process.communicate(command)
    # return response
    response = response.decode('utf-8')
    return(response)

class tag_database:
    def __init__(self, *args, **kwargs):
        self.data = {}
        self.data_file = ""

    # save database file
    def db_save(self):
        with open(DATA_DIR + DB_NAME,'wb') as f:
            pk.dump(self.data,f)

    # load database file
    def db_load(self):
        with open(DATA_DIR + DB_NAME,'rb') as f:
            temp = pk.load(f)
            return(temp)

    # check if database exists and load it
    def db_check(self):
        db_exists = Path(DATA_DIR + DB_NAME).is_file()
        if not db_exists:
            # ensure data path exists for saving the data later
            Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
        else:
            # load the data
            self.data = self.db_load()

    # check if tag exists in the data
    def tag_check(self,tag_name):
        if tag_name in list(self.data.keys()):
            pass
        else:
            self.data[tag_name] = []

    # update the database with new tags
    def update_data(self,tag_name,new_data):
        self.data[tag_name] = new_data

    # reconcile the old and new data
    def reconcile_data(self,tag_name,new_data):
        # extract what exists
        cur_data = self.data[tag_name]
        # extract new attributes
        new_tags = set(new_data) - set(cur_data)
        # extract attributes no longer tagged
        replace_tags = set(cur_data) - set(new_data)

        return({'TRUE':new_tags, 'FALSE':replace_tags})

    def reconcile_process(self,tag,ids,i):
        k = i
        # get difference
        res = self.reconcile_data(tag,ids)
        # process
        for each in res.items():
            if each[0] == 'TRUE' and len(each[1]) > 0:
                self.data_file = self.data_file + ',TRUE\n'.join(list(map(str,each[1]))) + ",TRUE\n"
                k = k + len(each[1])
            elif each[0] == 'FALSE' and len(each[1]) > 0:
                self.data_file = self.data_file + ',FALSE\n'.join(list(map(str,each[1]))) + ",FALSE\n"
                k = k + len(each[1])

        return(k)

    def cs_data_extraction(self):

        # build the SQL query
        temp = select_aid_template.substitute(cs_ids=IN_CS_IDS)
        qry = data_query_template.substitute(query=temp)
        # execute the whole thing
        cmd = qry.encode('utf-8')
        res_temp = bashCMD(cmd)
        res = list(map(lambda x: x.strip(),res_temp.split('\n')))[3:-3]

        return(res)

    def catalog_set_process(self,i):
        # catalog set attributes
        cs_ids = self.cs_data_extraction()

        # counter for number of changes
        k = len(cs_ids)

        if k > 0:
            cs_ids = list(map(int,cs_ids))

        # process catalog set tags
        self.tag_check(CS_TAG)
        i = i + self.reconcile_process(CS_TAG,cs_ids,i)

        return([i,cs_ids])

    # write data into the root jail
    def execute_flag_change(self):
        if len(self.data_file) > 0:
            with open(DATA_FILE,'w') as f:
                f.writelines(self.data_file)
            # write out the code into root jail
            with open(CODE_FILE,'w') as f:
                f.writelines(CODE_TEXT)
            # execute the code
            cmd = b"""sudo chroot "/opt/alation/alation" /bin/su - alation
            python /opt/alation/django/rosemeta/one_off_scripts/pii_change.py"""
            bashCMD(cmd)

            # clear the data_file
            self.data_file = ""