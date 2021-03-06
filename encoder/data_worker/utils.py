#===============================================================================
from gearman import GearmanWorker, DataEncoder
from converter import Converter
import json
import env_settings
import sys, os
import os
import glob
import pyrax
import pyrax.exceptions as exc
import pyrax.utils as utils
import MySQLdb
import urllib
import traceback
import uuid
#-------------------------------------------------------------------------------
pyrax.set_setting("identity_type", "rackspace")
creds_file = os.path.expanduser("~/pyrax_rc")
region = env_settings.REGION.upper()
pyrax.set_credential_file(creds_file, region)

cf = pyrax.cloudfiles

# Only use service net for cloudfiles if on public cloud, not private
if env_settings.USE_SNET == "true":
    snet_cf = pyrax.connect_to_cloudfiles(region, public=False)
else:
    snet_cf = cf

uploaded_cont_name = "uploaded"
completed_cont_name = "completed"

c = Converter()
table="converter_encodingjob"
#-------------------------------------------------------------------------------
class JSONDataEncoder(DataEncoder):
    @classmethod
    def encode(cls, encodable_object):
        return json.dumps(encodable_object)
    
    @classmethod
    def decode(cls, decodable_string):
        return json.loads(decodable_string)
#-------------------------------------------------------------------------------
class JSONGearmanWorker(GearmanWorker):
    data_encoder = JSONDataEncoder

    def on_job_execute(self, current_job):
        print "Job started"
        return super(JSONGearmanWorker, self).on_job_execute(current_job)

    def on_job_exception(self, current_job, exc_info):
        print "Job failed"
        ex_type, ex, tb = exc_info
        print ex_type, ex, traceback.print_tb(tb)
        return super(JSONGearmanWorker, self).on_job_exception(\
                current_job, exc_info)

    def on_job_complete(self, current_job, job_result):
        print "Job completed"
        return super(JSONGearmanWorker, self).send_job_complete(\
                current_job, job_result)

    def after_poll(self, any_activity):
        # Return True if you want to continue polling, replaces callback_fxn
        return True
#-------------------------------------------------------------------------------
class Utils:
#-------------------------------------------------------------------------------
    def __init__(self):
        None
#-------------------------------------------------------------------------------
    def mysql_call(self, cmd):
        db = MySQLdb.connect(
                host = env_settings.MYSQL_HOST,
                user = env_settings.MYSQL_USER,
                passwd = env_settings.MYSQL_PASSWORD,
                db = env_settings.MYSQL_DB
                )

        cur = db.cursor(MySQLdb.cursors.DictCursor)
        cur.execute(cmd)
        db.commit()

        results = cur.fetchall()

        cur.close()
        db.close()

        return results
#-------------------------------------------------------------------------------
    def update_job_status(self, status, job_id):
        cmd = "UPDATE %s SET status='%s' WHERE id=%s;" % \
                (table, status, job_id)
        results = self.mysql_call(cmd)

        return results
#-------------------------------------------------------------------------------
    def cleanup(self, filepath):
        for fl in glob.glob(filepath + "*"):
            os.remove(fl)
#-------------------------------------------------------------------------------
    def encode_job(self, gearman_worker, gearman_job):
        passed_data = gearman_job.data

        job_id = passed_data['job_id']

        # pull job info
        cmd = "SELECT * FROM %s WHERE id=%s;" % (table, job_id)
        job = self.mysql_call(cmd)[0]

        orig_uuid = job['orig_uuid']
        urls = json.loads(job['urls'])

        path = '/tmp/' + orig_uuid
        urllib.urlretrieve(urls['original_snet'], path)

        # update status
        self.update_job_status("processing", job_id)

        # start encoding job
        self.encode(job_id, path)
        self.update_job_status("complete", job_id)
        
        return None
#-------------------------------------------------------------------------------
    def encode(self, job_id, media):
        cmd = "SELECT * FROM %s WHERE id=%s;" % (table, job_id)
        job = self.mysql_call(cmd)[0]

        orig_uuid = job['orig_uuid']

        formats = { 
                'avi': ('aac', 'mpeg2'),
                'mkv': ('aac', 'h264'),
                'ogg': ('vorbis', 'theora'),
                'webm': ('vorbis', 'vp8')
                }

        for format,codecs in formats.items():
            output_path = "/tmp/" + orig_uuid + "." + format
            conv = c.convert(media, output_path,
                    {
                        'format': format,
                        'audio': { 'codec': codecs[0] },
                        'video': { 'codec': codecs[1] }
                        })
            for timecode in conv:
                status = "Encoding %s @ %d%%" % (format, timecode)
                self.update_job_status(status, job_id)
            self.update_job_status("uploading %s" % format, job_id)
            self.upload_encoding(job_id, format)
            self.update_job_status("upload of %s done" % format, job_id)

        base_path = "/tmp/" + orig_uuid
        self.cleanup(base_path)
#-------------------------------------------------------------------------------
    def upload_encoding(self, job_id, format):
        cmd = "SELECT * FROM %s WHERE id=%s;" % (table, job_id)
        job = self.mysql_call(cmd)[0]

        orig_uuid = job['orig_uuid']
        filename = job['filename']
        urls = json.loads(job['urls'])

        obj_name = str(uuid.uuid4())
        base_path = "/tmp/" + orig_uuid
        filepath = base_path + "." + format

        snet_cf.upload_file(completed_cont_name, 
                file_or_path=filepath, obj_name=obj_name)

        root, ext = os.path.splitext(filename)
        encoded_filename = root + "." + format
        public_dl_url = cf.get_temp_url(completed_cont_name, obj_name, 
                60*60*3, 'GET') + "&filename=" + encoded_filename
        snet_dl_url = snet_cf.get_temp_url(completed_cont_name, obj_name,
                60*60*3, 'GET') + "&filename=" + encoded_filename

        urls[format] = public_dl_url
        urls[format + "_snet"] = snet_dl_url
        urls_str = json.dumps(urls)

        cmd = "UPDATE %s SET urls='%s' WHERE id=%s;" % \
                (table, urls_str, job_id)
        results = self.mysql_call(cmd)

        self.cleanup(filepath)
#-------------------------------------------------------------------------------
    def register_job(self, gm_servers, task_name, task_function):
        gm_worker = JSONGearmanWorker(gm_servers)
        gm_worker.register_task(task_name, task_function)
        gm_worker.work()
#-------------------------------------------------------------------------------
#===============================================================================
