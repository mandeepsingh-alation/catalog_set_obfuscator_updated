import os
#### Start of settings you ned to change ####
# Catalog Sets to be obfuscated
# CSV string, e.g. '14,12,3'
IN_CS_IDS = '1'
#### End of settings you ned to change   ####

# Path for application database
DATA_DIR = os.getcwd() + '/data/'

# Catalog set identifier
CS_TAG = 'cs_cols'
# Sleep timer between runs in seconds
SLEEP_TIME = 2

# Application database name
DB_NAME = 'tag_db'
# Complete path and filename for the CSV needed by the utility
DATA_FILE = '/opt/alation/alation/data1/tmp/pii_change_data.csv'
# Complete path and filename for the python file needed by the utility
CODE_FILE = '/opt/alation/alation/opt/alation/django/rosemeta/one_off_scripts/pii_change.py'
# Code to be written into the root jail
CODE_TEXT = """import csv
from time import sleep
import bootstrap_rosemeta
from rosemeta.models.models_data import Attribute

# define function to set column as PII
def pii_change(a_id,flag):
    a = Attribute.objects.get(id=a_id)
    a.sensitive = flag
    a.save(update_fields=['sensitive'])

data = []
with open('/tmp/pii_change_data.csv','r') as f:
    reader = csv.reader(f)
    for row in reader:
        data.append(row)

# process the data
for i in range(0,len(data)):
    data[i][0] = int(data[i][0])
    if data[i][1].lower() == 'true':
        data[i][1] = True
    else:
        data[i][1] = False

# apply changes
for row in data:
    pii_change(row[0],row[1])

print('Task Complete')
"""
