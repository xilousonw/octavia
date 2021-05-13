import pycurl
import logging
import cStringIO
import json
import requests


logging.basicConfig(level=logging.INFO)
logging.getLogger('suds.client').setLevel(logging.DEBUG)
LOG = logging.getLogger(__name__)


def get_logger(logger_name, log_file, level=logging.INFO, mode='a'):
    formatter = logging.Formatter('%(message)s')
    fileHandler = logging.FileHandler(log_file, mode=mode)
    fileHandler.setFormatter(formatter)

    vlog = logging.getLogger(logger_name)
    vlog.setLevel(level)
    vlog.addHandler(fileHandler)

    return vlog



DRIVER_NAME = 'dptech'


OPTS = [
    cfg.StrOpt('controller_ip', default='10.27.24.20'),
    cfg.StrOpt('tenant_name', default='admin'),
    cfg.StrOpt('tenant_passwd', default='1q2w3e4r'),

    cfg.StrOpt('username', default='admin'),
    cfg.StrOpt('password', default='admin_default', secret=True),
    cfg.StrOpt('lb_device', default='10.27.24.204'),
    cfg.StrOpt('interface', default='vlan-if'),
    cfg.StrOpt('if_mode', default='vlan'),
    cfg.StrOpt('mac_address', default=False),
    cfg.StrOpt('device_type', default='adx'),
    cfg.StrOpt('dpx_lb_slot', default='0'),
    cfg.StrOpt('device_version', default='shen3'),
    cfg.StrOpt('localhost', default='localhost')
]
cfg.CONF.register_opts(OPTS, 'dptech')




class LBCommon:
    def __init__(self):
        pass

    def get_token(self):
        buf = cStringIO.StringIO()
        jsoncode = """
        {
            "auth": { 
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": "%s",
                            "domain": {"name": "default"},
                            "password": "%s"
                        }
                    }
                },
                "scope": {
                    "project": {
                        "domain": {"name": "default"},
                        "name": "admin"
                    }
                }
            }
        }
        """ % (self.tenant_name, self.tenant_passwd)
        url = 'http://' + self.controller_ip + ':5000/v3/auth/tokens'
        c = pycurl.Curl()
        c.setopt(c.URL, url)
        c.setopt(c.HTTPHEADER, ['Content-Type:application/json'])
        c.setopt(c.WRITEFUNCTION, buf.write)
        c.setopt(c.HEADER, 1)
        c.setopt(c.HEADERFUNCTION, buf.write)
        c.setopt(c.SSL_VERIFYPEER, 0)
        c.setopt(c.POSTFIELDS, jsoncode)
        c.perform()
        c.close()
        res = buf.getvalue()
        LOG.debug('get token url %s', url)
        token = res.split("X-Subject-Token:")[1]
        token = token.strip()
        return token

    def notify_dp_restful(self, action, resource, body_data={}):
        ip = self.device
        utils.check_device_reachable(ip=ip)
        url = 'http://%(ip)s/func/web_main/api/' % {'ip': ip} + resource

        buf = cStringIO.StringIO()
        LOG.debug('url is %s, body_data is %s, action is %s', url, body_data, action)
        c = pycurl.Curl()
        c.setopt(c.URL, str(url))
        c.setopt(pycurl.USERPWD, '%s:%s' % (self.username, self.password))

        c.setopt(c.HTTPHEADER, ['Content-Type:application/json', \
                                'Accept:application/json', 'Expect:'])

        c.setopt(c.WRITEFUNCTION, buf.write)
        c.setopt(c.SSL_VERIFYPEER, 0)
        c.setopt(c.CUSTOMREQUEST, action)
        post_fields = json.dumps(body_data)
        if action != "GET":
            c.setopt(c.POSTFIELDS, post_fields)
        c.perform()
        buf_value = buf.getvalue()
        LOG.info('notify_dp_restful buf_value %s', buf_value)
        if buf_value:
            try:
                tmp = json.loads(buf_value,
                                 object_pairs_hook=OrderedDict)
                d = json.dumps(tmp, indent=4)
                c.close()
                buf.close()
                return json.loads(d)
            except ValueError, e:
                LOG.error(e)
        c.close()
        buf.close()
        LOG.info('over')
        return []


















