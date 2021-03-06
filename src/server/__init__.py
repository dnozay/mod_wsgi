from __future__ import print_function, division, absolute_import

import os
import sys
import shutil
import subprocess
import optparse
import math
import signal
import threading
import atexit
import imp
import pwd
import grp

try:
    import Queue as queue
except ImportError:
    import queue

from . import apxs_config

_py_version = '%s%s' % sys.version_info[:2]
_py_soabi = ''
_py_soext = '.so'

try:
    import imp
    import sysconfig

    _py_soabi = sysconfig.get_config_var('SOABI')
    _py_soext = sysconfig.get_config_var('SO')

except ImportError:
    pass

MOD_WSGI_SO = 'mod_wsgi-py%s%s' % (_py_version, _py_soext)
MOD_WSGI_SO = os.path.join(os.path.dirname(__file__), MOD_WSGI_SO)

if not os.path.exists(MOD_WSGI_SO) and _py_soabi:
    MOD_WSGI_SO = 'mod_wsgi-py%s.%s%s' % (_py_version, _py_soabi, _py_soext)
    MOD_WSGI_SO = os.path.join(os.path.dirname(__file__), MOD_WSGI_SO)

def where():
    return MOD_WSGI_SO

def default_run_user():
   return pwd.getpwuid(os.getuid()).pw_name

def default_run_group():
   return grp.getgrgid(pwd.getpwuid(os.getuid()).pw_gid).gr_name

def find_program(names, default=None, paths=[]):
    for name in names:
        for path in os.environ['PATH'].split(':') + paths:
            program = os.path.join(path, name)
            if os.path.exists(program):
                return program
    return default

def find_mimetypes():
    import mimetypes
    for name in mimetypes.knownfiles:
        if os.path.exists(name):
            return name
            break
    else:
        return name

APACHE_GENERAL_CONFIG = """
<IfModule !version_module>
LoadModule version_module '%(modules_directory)s/mod_version.so'
</IfModule>

ServerName %(host)s
ServerRoot '%(server_root)s'
PidFile '%(pid_file)s'

<IfVersion >= 2.4>
DefaultRuntimeDir '%(server_root)s'
</IfVersion>

ServerSignature Off

User ${WSGI_RUN_USER}
Group ${WSGI_RUN_GROUP}

<IfDefine WSGI_LISTENER_HOST>
Listen %(host)s:%(port)s
</IfDefine>
<IfDefine !WSGI_LISTENER_HOST>
Listen %(port)s
</IfDefine>

<IfVersion < 2.4>
LockFile '%(server_root)s/accept.lock'
</IfVersion>

<IfVersion >= 2.4>
<IfDefine WSGI_WITH_PHP5>
<IfModule !mpm_event_module>
<IfModule !mpm_worker_module>
<IfModule !mpm_prefork_module>
<IfDefine WSGI_MPM_EXISTS_PREFORK_MODULE>
LoadModule mpm_prefork_module '%(modules_directory)s/mod_mpm_prefork.so'
</IfDefine>
</IfModule>
</IfModule>
</IfModule>
</IfDefine>
</IfVersion>

<IfVersion >= 2.4>
<IfModule !mpm_event_module>
<IfModule !mpm_worker_module>
<IfModule !mpm_prefork_module>
<IfDefine WSGI_MPM_ENABLE_EVENT_MODULE>
LoadModule mpm_event_module '%(modules_directory)s/mod_mpm_event.so'
</IfDefine>
<IfDefine WSGI_MPM_ENABLE_WORKER_MODULE>
LoadModule mpm_worker_module '%(modules_directory)s/mod_mpm_worker.so'
</IfDefine>
<IfDefine WSGI_MPM_ENABLE_PREFORK_MODULE>
LoadModule mpm_prefork_module '%(modules_directory)s/mod_mpm_prefork.so'
</IfDefine>
</IfModule>
</IfModule>
</IfModule>
</IfVersion>

<IfVersion >= 2.4>
<IfModule !access_compat_module>
LoadModule access_compat_module '%(modules_directory)s/mod_access_compat.so'
</IfModule>
<IfModule !unixd_module>
LoadModule unixd_module '%(modules_directory)s/mod_unixd.so'
</IfModule>
<IfModule !authn_core_module>
LoadModule authn_core_module '%(modules_directory)s/mod_authn_core.so'
</IfModule>
<IfModule !authz_core_module>
LoadModule authz_core_module '%(modules_directory)s/mod_authz_core.so'
</IfModule>
</IfVersion>

<IfModule !authz_host_module>
LoadModule authz_host_module '%(modules_directory)s/mod_authz_host.so'
</IfModule>
<IfModule !mime_module>
LoadModule mime_module '%(modules_directory)s/mod_mime.so'
</IfModule>
<IfModule !rewrite_module>
LoadModule rewrite_module '%(modules_directory)s/mod_rewrite.so'
</IfModule>
<IfModule !alias_module>
LoadModule alias_module '%(modules_directory)s/mod_alias.so'
</IfModule>
<IfModule !dir_module>
LoadModule dir_module '%(modules_directory)s/mod_dir.so'
</IfModule>
<IfModule !env_module>
LoadModule env_module '%(modules_directory)s/mod_env.so'
</IfModule>

<IfDefine WSGI_COMPRESS_RESPONSES>
<IfModule !deflate_module>
LoadModule deflate_module '%(modules_directory)s/mod_deflate.so'
</IfModule>
</IfDefine>

<IfDefine WSGI_AUTH_USER>
<IfModule !auth_basic_module>
LoadModule auth_basic_module '%(modules_directory)s/mod_auth_basic.so'
</IfModule>
<IfModule !auth_digest_module>
LoadModule auth_digest_module '%(modules_directory)s/mod_auth_digest.so'
</IfModule>
<IfModule !authz_user_module>
LoadModule authz_user_module '%(modules_directory)s/mod_authz_user.so'
</IfModule>
</IfDefine>

<IfModule mpm_prefork_module>
<IfDefine WSGI_WITH_PHP5>
<IfModule !php5_module>
Loadmodule php5_module '%(modules_directory)s/libphp5.so'
</IfModule>
AddHandler application/x-httpd-php .php
</IfDefine>
</IfModule>

LoadModule wsgi_module '%(mod_wsgi_so)s'

<IfDefine WSGI_SERVER_METRICS>
<IfModule !status_module>
LoadModule status_module '%(modules_directory)s/mod_status.so'
</IfModule>
</IfDefine>

<IfVersion < 2.4>
DefaultType text/plain
</IfVersion>

TypesConfig '%(mime_types)s'

HostnameLookups Off
MaxMemFree 64
Timeout %(socket_timeout)s
ListenBacklog %(server_backlog)s

LimitRequestBody %(limit_request_body)s

<Directory />
    AllowOverride None
    Order deny,allow
    Deny from all
</Directory>

WSGIPythonHome '%(python_home)s'

<IfDefine !ONE_PROCESS>
WSGIRestrictEmbedded On
WSGISocketPrefix %(server_root)s/wsgi
<IfDefine WSGI_MULTIPROCESS>
WSGIDaemonProcess %(host)s:%(port)s \\
   display-name='%(process_name)s' \\
   home='%(working_directory)s' \\
   processes=%(processes)s \\
   threads=%(threads)s \\
   maximum-requests=%(maximum_requests)s \\
   python-eggs='%(python_eggs)s' \\
   lang='%(lang)s' \\
   locale='%(locale)s' \\
   listen-backlog=%(daemon_backlog)s \\
   queue-timeout=%(queue_timeout)s \\
   socket-timeout=%(socket_timeout)s \\
   connect-timeout=%(connect_timeout)s \\
   request-timeout=%(request_timeout)s \\
   inactivity-timeout=%(inactivity_timeout)s \\
   deadlock-timeout=%(deadlock_timeout)s \\
   graceful-timeout=%(graceful_timeout)s \\
   shutdown-timeout=%(shutdown_timeout)s \\
   send-buffer-size=%(send_buffer_size)s \\
   receive-buffer-size=%(receive_buffer_size)s \\
   header-buffer-size=%(header_buffer_size)s \\
   server-metrics=%(daemon_server_metrics_flag)s
</IfDefine>
<IfDefine !WSGI_MULTIPROCESS>
WSGIDaemonProcess %(host)s:%(port)s \\
   display-name='%(process_name)s' \\
   home='%(working_directory)s' \\
   threads=%(threads)s \\
   maximum-requests=%(maximum_requests)s \\
   python-eggs='%(python_eggs)s' \\
   lang='%(lang)s' \\
   locale='%(locale)s' \\
   listen-backlog=%(daemon_backlog)s \\
   queue-timeout=%(queue_timeout)s \\
   socket-timeout=%(socket_timeout)s \\
   connect-timeout=%(connect_timeout)s \\
   request-timeout=%(request_timeout)s \\
   inactivity-timeout=%(inactivity_timeout)s \\
   deadlock-timeout=%(deadlock_timeout)s \\
   graceful-timeout=%(graceful_timeout)s \\
   shutdown-timeout=%(shutdown_timeout)s \\
   send-buffer-size=%(send_buffer_size)s \\
   receive-buffer-size=%(receive_buffer_size)s \\
   header-buffer-size=%(header_buffer_size)s \\
   server-metrics=%(daemon_server_metrics_flag)s
</IfDefine>
</IfDefine>

WSGICallableObject '%(callable_object)s'
WSGIPassAuthorization On
WSGIMapHEADToGET %(map_head_to_get)s

<IfDefine ONE_PROCESS>
WSGIRestrictStdin Off
</IfDefine>

<IfDefine WSGI_SERVER_METRICS>
ExtendedStatus On
</IfDefine>

<IfDefine WSGI_SERVER_STATUS>
<Location /server-status>
    SetHandler server-status
    Order deny,allow
    Deny from all
    Allow from localhost
</Location>
</IfDefine>

<IfDefine WSGI_KEEP_ALIVE>
KeepAlive On
KeepAliveTimeout %(keep_alive_timeout)s
</IfDefine>
<IfDefine !WSGI_KEEP_ALIVE>
KeepAlive Off
</IfDefine>

<IfDefine WSGI_COMPRESS_RESPONSES>
AddOutputFilterByType DEFLATE text/plain
AddOutputFilterByType DEFLATE text/html
AddOutputFilterByType DEFLATE text/xml
AddOutputFilterByType DEFLATE text/css
AddOutputFilterByType DEFLATE text/javascript
AddOutputFilterByType DEFLATE application/xhtml+xml
AddOutputFilterByType DEFLATE application/javascript
</IfDefine>

<IfDefine WSGI_ROTATE_LOGS>
ErrorLog "|%(rotatelogs_executable)s \\
    %(error_log)s.%%Y-%%m-%%d-%%H_%%M_%%S %(max_log_size)sM"
</IfDefine>
<IfDefine !WSGI_ROTATE_LOGS>
ErrorLog '%(error_log)s'
</IfDefine>
LogLevel %(log_level)s

<IfDefine WSGI_ACCESS_LOG>
<IfModule !log_config_module>
LoadModule log_config_module %(modules_directory)s/mod_log_config.so
</IfModule>
LogFormat "%%h %%l %%u %%t \\"%%r\\" %%>s %%b" common
<IfDefine WSGI_ROTATE_LOGS>
CustomLog "|%(rotatelogs_executable)s \\
    %(log_directory)s/access_log.%%Y-%%m-%%d-%%H_%%M_%%S %(max_log_size)sM" common
</IfDefine>
<IfDefine !WSGI_ROTATE_LOGS>
CustomLog "%(log_directory)s/access_log" common
</IfDefine>
</IfDefine>

<IfDefine WSGI_WITH_SSL>
<IfModule !ssl_module>
LoadModule ssl_module %(modules_directory)s/mod_ssl.so
</IfModule>
</IfDefine>

<IfModule mpm_prefork_module>
<IfDefine !ONE_PROCESS>
ServerLimit %(prefork_server_limit)s
StartServers %(prefork_start_servers)s
MaxClients %(prefork_max_clients)s
MinSpareServers %(prefork_min_spare_servers)s
MaxSpareServers %(prefork_max_spare_servers)s
</IfDefine>
<IfDefine ONE_PROCESS>
ServerLimit 1
StartServers 1
MaxClients 1
MinSpareServers 1
MaxSpareServers 1
</IfDefine>
MaxRequestsPerChild 0
</IfModule>

<IfModule mpm_worker_module>
<IfDefine !ONE_PROCESS>
ServerLimit %(worker_server_limit)s
ThreadLimit %(worker_thread_limit)s
StartServers %(worker_start_servers)s
MaxClients %(worker_max_clients)s
MinSpareThreads %(worker_min_spare_threads)s
MaxSpareThreads %(worker_max_spare_threads)s
ThreadsPerChild %(worker_threads_per_child)s
</IfDefine>
<IfDefine ONE_PROCESS>
ServerLimit 1
ThreadLimit 1
StartServers 1 
MaxClients 1
MinSpareThreads 1
MaxSpareThreads 1
ThreadsPerChild 1
</IfDefine>
MaxRequestsPerChild 0
ThreadStackSize 262144
</IfModule>

<IfModule mpm_event_module>
<IfDefine !ONE_PROCESS>
ServerLimit %(worker_server_limit)s
ThreadLimit %(worker_thread_limit)s
StartServers %(worker_start_servers)s
MaxClients %(worker_max_clients)s
MinSpareThreads %(worker_min_spare_threads)s
MaxSpareThreads %(worker_max_spare_threads)s
ThreadsPerChild %(worker_threads_per_child)s
</IfDefine>
<IfDefine ONE_PROCESS>
ServerLimit 1
ThreadLimit 1
StartServers 1
MaxClients 1
MinSpareThreads 1
MaxSpareThreads 1
ThreadsPerChild 1
</IfDefine>
MaxRequestsPerChild 0
ThreadStackSize 262144
</IfModule>

<IfDefine WSGI_VIRTUAL_HOST>

<IfVersion < 2.4>
NameVirtualHost *:%(port)s
</IfVersion>
<VirtualHost _default_:%(port)s>
<Location />
Order deny,allow
Deny from all
<IfDefine WSGI_ALLOW_LOCALHOST>
Allow from localhost
</IfDefine>
</Location>
</VirtualHost>
<IfDefine !WSGI_HTTPS_ONLY>
<VirtualHost *:%(port)s>
ServerName %(server_name)s
<IfDefine WSGI_SERVER_ALIAS>
ServerAlias %(server_aliases)s
</IfDefine>
</VirtualHost>
<IfDefine WSGI_REDIRECT_WWW>
<VirtualHost *:%(port)s>
ServerName %(parent_domain)s
Redirect permanent / http://%(server_name)s:%(port)s/
</VirtualHost>
</IfDefine>
</IfDefine>

<IfDefine WSGI_HTTPS_ONLY>
<VirtualHost *:%(port)s>
ServerName %(server_name)s
<IfDefine WSGI_SERVER_ALIAS>
ServerAlias %(server_aliases)s
RewriteEngine On
RewriteCond %%{HTTPS} off
RewriteRule (.*) https://%%{HTTP_HOST}%%{REQUEST_URI}
</IfDefine>
</VirtualHost>
<IfDefine WSGI_REDIRECT_WWW>
<VirtualHost *:%(port)s>
ServerName %(parent_domain)s
RewriteEngine On
RewriteCond %%{HTTPS} off
RewriteRule (.*) https://%%{HTTP_HOST}%%{REQUEST_URI}
</VirtualHost>
</IfDefine>
</IfDefine>

</IfDefine>

<IfDefine WSGI_VIRTUAL_HOST>

<IfDefine WSGI_WITH_SSL>
<IfDefine WSGI_LISTENER_HOST>
Listen %(host)s:%(ssl_port)s
</IfDefine>
<IfDefine !WSGI_LISTENER_HOST>
Listen %(ssl_port)s
</IfDefine>
<IfVersion < 2.4>
NameVirtualHost *:%(ssl_port)s
</IfVersion>
<VirtualHost _default_:%(ssl_port)s>
<Location />
Order deny,allow
Deny from all
<IfDefine WSGI_ALLOW_LOCALHOST>
Allow from localhost
</IfDefine>
</Location>
SSLEngine On
SSLCertificateFile %(ssl_certificate)s.crt
SSLCertificateKeyFile %(ssl_certificate)s.key
</VirtualHost>
<VirtualHost *:%(ssl_port)s>
ServerName %(server_name)s
<IfDefine WSGI_SERVER_ALIAS>
ServerAlias %(server_aliases)s
</IfDefine>
SSLEngine On
SSLCertificateFile %(ssl_certificate)s.crt
SSLCertificateKeyFile %(ssl_certificate)s.key
</VirtualHost>
<IfDefine WSGI_REDIRECT_WWW>
<VirtualHost *:%(ssl_port)s>
ServerName %(parent_domain)s
Redirect permanent / https://%(server_name)s:%(ssl_port)s/
SSLEngine On
SSLCertificateFile %(ssl_certificate)s.crt
SSLCertificateKeyFile %(ssl_certificate)s.key
</VirtualHost>
</IfDefine>
</IfDefine>

</IfDefine>

DocumentRoot '%(document_root)s'

<Directory '%(server_root)s'>
<Files handler.wsgi>
    Order allow,deny
    Allow from all
</Files>
</Directory>

<Directory '%(document_root)s%(mount_point)s'>
<IfDefine WSGI_DIRECTORY_INDEX>
    DirectoryIndex %(directory_index)s
</IfDefine>
    RewriteEngine On
    RewriteCond %%{REQUEST_FILENAME} !-f
<IfDefine WSGI_DIRECTORY_INDEX>
    RewriteCond %%{REQUEST_FILENAME} !-d
</IfDefine>
<IfDefine WSGI_SERVER_STATUS>
    RewriteCond %%{REQUEST_URI} !/server-status
</IfDefine>
    RewriteRule .* - [H=wsgi-handler]
    Order allow,deny
    Allow from all
</Directory>

<IfDefine WSGI_ERROR_OVERRIDE>
WSGIErrorOverride On
</IfDefine>

<IfDefine WSGI_AUTH_USER>
<Location />
    AuthType %(auth_type)s
    AuthName '%(host)s:%(port)s'
    Auth%(auth_type)sProvider wsgi
    WSGIAuthUserScript '%(auth_user_script)s'
<IfDefine WSGI_AUTH_GROUP>
    WSGIAuthGroupScript '%(auth_group_script)s'
</IfDefine>
<IfVersion < 2.4>
    Require valid-user
<IfDefine WSGI_AUTH_GROUP>
    Require wsgi-group '%(auth_group)s'
</IfDefine>
</IfVersion>
<IfVersion >= 2.4>
    <RequireAll>
    Require valid-user
<IfDefine WSGI_AUTH_GROUP>
    Require wsgi-group '%(auth_group)s'
</IfDefine>
    </RequireAll>
</IfVersion>
</Location>
</IfDefine>

<IfDefine !ONE_PROCESS>
WSGIHandlerScript wsgi-handler '%(server_root)s/handler.wsgi' \\
    process-group='%(host)s:%(port)s' application-group=%%{GLOBAL}
WSGIImportScript '%(server_root)s/handler.wsgi' \\
    process-group='%(host)s:%(port)s' application-group=%%{GLOBAL}
</IfDefine>

<IfDefine ONE_PROCESS>
WSGIHandlerScript wsgi-handler '%(server_root)s/handler.wsgi' \\
    process-group='%%{GLOBAL}' application-group=%%{GLOBAL}
WSGIImportScript '%(server_root)s/handler.wsgi' \\
    process-group='%%{GLOBAL}' application-group=%%{GLOBAL}
</IfDefine>
"""

APACHE_ALIAS_DIRECTORY_CONFIG = """
Alias '%(mount_point)s' '%(directory)s'

<Directory '%(directory)s'>
    Order allow,deny
    Allow from all
</Directory>
"""

APACHE_ALIAS_FILENAME_CONFIG = """
Alias '%(mount_point)s' '%(directory)s/%(filename)s'

<Directory '%(directory)s'>
<Files '%(filename)s'>
    Order allow,deny
    Allow from all
</Files>
</Directory>
"""

APACHE_ALIAS_DOCUMENTATION = """
Alias /__wsgi__/docs '%(documentation_directory)s'
Alias /__wsgi__/images '%(images_directory)s'

<Directory '%(documentation_directory)s'>
    DirectoryIndex index.html
    Order allow,deny
    Allow from all
</Directory>

<Directory '%(images_directory)s'>
    Order allow,deny
    Allow from all
</Directory>
"""

APACHE_ERROR_DOCUMENT_CONFIG = """
ErrorDocument '%(status)s' '%(document)s'
"""

APACHE_SETENV_CONFIG = """
SetEnv '%(name)s' '%(value)s'
"""

APACHE_PASSENV_CONFIG = """
PassEnv '%(name)s'
"""

APACHE_INCLUDE_CONFIG = """
Include '%(filename)s'
"""

APACHE_TOOLS_CONFIG = """
WSGIDaemonProcess express display-name=%%{GROUP} threads=1 server-metrics=On
"""

APACHE_METRICS_CONFIG = """
WSGIImportScript '%(server_root)s/server-metrics.py' \\
    process-group=express application-group=server-metrics
"""

APACHE_WDB_CONFIG = """
WSGIImportScript '%(server_root)s/wdb-server.py' \\
    process-group=express application-group=wdb-server
"""

def generate_apache_config(options):
    with open(options['httpd_conf'], 'w') as fp:
        print(APACHE_GENERAL_CONFIG % options, file=fp)

        if options['url_aliases']:
            for mount_point, target in sorted(options['url_aliases'],
                    reverse=True):
                target = os.path.abspath(target)

                if os.path.isdir(target):
                    directory = target

                    print(APACHE_ALIAS_DIRECTORY_CONFIG % dict(
                            mount_point=mount_point, directory=directory),
                            file=fp)

                else:
                    directory = os.path.dirname(target)
                    filename = os.path.basename(target)

                    print(APACHE_ALIAS_FILENAME_CONFIG % dict(
                            mount_point=mount_point, directory=directory,
                            filename=filename), file=fp)

        if options['enable_docs']:
            print(APACHE_ALIAS_DOCUMENTATION % options, file=fp)

        if options['error_documents']:
            for status, document in options['error_documents']:
                print(APACHE_ERROR_DOCUMENT_CONFIG % dict(status=status,
                        document=document.replace("'", "\\'")), file=fp)

        if options['setenv_variables']:
            for name, value in options['setenv_variables']:
                print(APACHE_SETENV_CONFIG % dict(name=name, value=value),
                        file=fp)

        if options['passenv_variables']:
            for name in options['passenv_variables']:
                print(APACHE_PASSENV_CONFIG % dict(name=name), file=fp)

        if options['include_files']:
            for filename in options['include_files']:
                filename = os.path.abspath(filename)
                print(APACHE_INCLUDE_CONFIG % dict(filename=filename),
                        file=fp)

        if options['with_newrelic_platform'] or options['with_wdb']:
            print(APACHE_TOOLS_CONFIG % options, file=fp)

        if options['with_newrelic_platform']:
            print(APACHE_METRICS_CONFIG % options, file=fp)

        if options['with_wdb']:
            print(APACHE_WDB_CONFIG % options, file=fp)

_interval = 1.0
_times = {}
_files = []

_running = False
_queue = queue.Queue()
_lock = threading.Lock()

def _restart(path):
    _queue.put(True)
    prefix = 'monitor (pid=%d):' % os.getpid()
    print('%s Change detected to "%s".' % (prefix, path), file=sys.stderr)
    print('%s Triggering process restart.' % prefix, file=sys.stderr)
    os.kill(os.getpid(), signal.SIGINT)

def _modified(path):
    try:
        # If path doesn't denote a file and were previously
        # tracking it, then it has been removed or the file type
        # has changed so force a restart. If not previously
        # tracking the file then we can ignore it as probably
        # pseudo reference such as when file extracted from a
        # collection of modules contained in a zip file.

        if not os.path.isfile(path):
            return path in _times

        # Check for when file last modified.

        mtime = os.stat(path).st_mtime
        if path not in _times:
            _times[path] = mtime

        # Force restart when modification time has changed, even
        # if time now older, as that could indicate older file
        # has been restored.

        if mtime != _times[path]:
            return True
    except Exception:
        # If any exception occured, likely that file has been
        # been removed just before stat(), so force a restart.

        return True

    return False

def _monitor():
    global _files

    while True:
        # Check modification times on all files in sys.modules.

        for module in list(sys.modules.values()):
            if not hasattr(module, '__file__'):
                continue
            path = getattr(module, '__file__')
            if not path:
                continue
            if os.path.splitext(path)[1] in ['.pyc', '.pyo', '.pyd']:
                path = path[:-1]
            if _modified(path):
                return _restart(path)

        # Check modification times on files which have
        # specifically been registered for monitoring.

        for path in _files:
            if _modified(path):
                return _restart(path)

        # Go to sleep for specified interval.

        try:
            return _queue.get(timeout=_interval)

        except queue.Empty:
            pass

_thread = threading.Thread(target=_monitor)
_thread.setDaemon(True)

def _exiting():
    try:
        _queue.put(True)
    except Exception:
        pass
    _thread.join()

def track_changes(path):
    if not path in _files:
        _files.append(path)

def start_reloader(interval=1.0):
    global _interval
    if interval < _interval:
        _interval = interval

    global _running
    _lock.acquire()
    if not _running:
        prefix = 'monitor (pid=%d):' % os.getpid()
        print('%s Starting change monitor.' % prefix, file=sys.stderr)
        _running = True
        _thread.start()
        atexit.register(_exiting)
    _lock.release()

class ApplicationHandler(object):

    def __init__(self, entry_point, application_type='script',
            callable_object='application', mount_point='/',
            with_newrelic=False, with_wdb=False, debug_mode=False):

        self.entry_point = entry_point
        self.application_type = application_type
        self.callable_object = callable_object
        self.mount_point = mount_point

        if application_type == 'module':
            __import__(entry_point)
            self.module = sys.modules[entry_point]
            self.application = getattr(self.module, callable_object)
            self.target = self.module.__file__
            parts = os.path.splitext(self.target)[-1]
            if parts[-1].lower() in ('.pyc', '.pyd', '.pyd'):
                self.target = parts[0] + '.py'

        elif application_type == 'paste':
            from paste.deploy import loadapp
            self.application = loadapp('config:%s' % entry_point)
            self.target = entry_point

        else:
            self.module = imp.new_module('__wsgi__')
            self.module.__file__ = entry_point

            with open(entry_point, 'r') as fp:
                code = compile(fp.read(), entry_point, 'exec',
                        dont_inherit=True)
                exec(code, self.module.__dict__)

            sys.modules['__wsgi__'] = self.module
            self.application = getattr(self.module, callable_object)
            self.target = entry_point

        try:
            self.mtime = os.path.getmtime(self.target)
        except Exception:
            self.mtime = None

        if with_newrelic:
            self.setup_newrelic()

        if with_wdb:
            self.setup_wdb()

        self.debug_mode = debug_mode

    def setup_newrelic(self):
        import newrelic.agent

        config_file = os.environ.get('NEW_RELIC_CONFIG_FILE')
        environment = os.environ.get('NEW_RELIC_ENVIRONMENT')

        global_settings = newrelic.agent.global_settings()
        if global_settings.log_file is None:
            global_settings.log_file = 'stderr'

        newrelic.agent.initialize(config_file, environment)
        newrelic.agent.register_application()

        self.application = newrelic.agent.WSGIApplicationWrapper(
                self.application)

    def setup_wdb(self):
        from wdb.ext import WdbMiddleware
        self.application = WdbMiddleware(self.application)

    def reload_required(self, environ):
        if self.debug_mode:
            return False

        try:
            mtime = os.path.getmtime(self.target)
        except Exception:
            mtime = None

        return mtime != self.mtime

    def handle_request(self, environ, start_response):
        # Strip out the leading component due to internal redirect in
        # Apache when using web application as fallback resource.

        script_name = environ.get('SCRIPT_NAME')
        path_info = environ.get('PATH_INFO')

        environ['SCRIPT_NAME'] = ''
        environ['PATH_INFO'] = script_name + path_info

        if self.mount_point != '/':
            if environ['PATH_INFO'].startswith(self.mount_point):
                environ['SCRIPT_NAME'] = self.mount_point
                environ['PATH_INFO'] = environ['PATH_INFO'][len(self.mount_point):]

        return self.application(environ, start_response)

    def __call__(self, environ, start_response):
        return self.handle_request(environ, start_response)

WSGI_HANDLER_SCRIPT = """
import mod_wsgi.server

entry_point = '%(entry_point)s'
application_type = '%(application_type)s'
callable_object = '%(callable_object)s'
mount_point = '%(mount_point)s'
with_newrelic = %(with_newrelic_agent)s
with_wdb = %(with_wdb)s
reload_on_changes = %(reload_on_changes)s
debug_mode = %(debug_mode)s

handler = mod_wsgi.server.ApplicationHandler(entry_point,
        application_type=application_type, callable_object=callable_object,
        mount_point=mount_point, with_newrelic=with_newrelic,
        with_wdb=with_wdb, debug_mode=debug_mode)

reload_required = handler.reload_required
handle_request = handler.handle_request

if reload_on_changes and not debug_mode:
    mod_wsgi.server.start_reloader()
"""

WSGI_DEFAULT_SCRIPT = """
CONTENT = b'''
<html>
<head>
<title>My web site runs on Malt Whiskey</title>
</head>
<body style="margin-top: 100px;">
<table align="center"; style="width: 850px;" border="0" cellpadding="30">
<tbody>
<tr>
<td>
<img style="width: 275px; height: 445px;"
  src="/__wsgi__/images/snake-whiskey.jpg">
</td>
<td style="text-align: center;">
<span style="font-family: Arial,Helvetica,sans-serif;
  font-weight: bold; font-size: 70px;">
My web site<br>runs on<br>Malt Whiskey<br>
<br>
</span>
<span style="font-family: Arial,Helvetica,sans-serif;
  font-weight: bold;">
For further information on configuring mod_wsgi,<br>
see the <a href="%(documentation_url)s">documentation</a>.
</span>
</td>
</tr>
</tbody>
</table>
</body>
</html>
'''

def application(environ, start_response):
    status = '200 OK'
    output = CONTENT

    response_headers = [('Content-type', 'text/html'),
                        ('Content-Length', str(len(output)))]
    start_response(status, response_headers)

    return [output]
"""

def generate_wsgi_handler_script(options):
    path = os.path.join(options['server_root'], 'handler.wsgi')
    with open(path, 'w') as fp:
        print(WSGI_HANDLER_SCRIPT % options, file=fp)

    path = os.path.join(options['server_root'], 'default.wsgi')
    with open(path, 'w') as fp:
        print(WSGI_DEFAULT_SCRIPT % options, file=fp)

SERVER_METRICS_SCRIPT = """
import logging

logging.basicConfig(level=logging.INFO,
    format='%%(name)s (pid=%%(process)d, level=%%(levelname)s): %%(message)s')

_logger = logging.getLogger(__name__)

try:
    from mod_wsgi.metrics.newrelic import Agent

    agent = Agent()
    agent.start()

except ImportError:
    _logger.fatal('The module mod_wsgi.metrics.newrelic is not available. '
            'The New Relic platform plugin has been disabled. Install the '
            '"mod_wsgi-metrics" package.')
"""

def generate_server_metrics_script(options):
    path = os.path.join(options['server_root'], 'server-metrics.py')
    with open(path, 'w') as fp:
        print(SERVER_METRICS_SCRIPT % options, file=fp)

WDB_SERVER_SCRIPT = """
from wdb_server import server
try:
    from wdb_server.sockets import handle_connection
except ImportError:
    from wdb_server.streams import handle_connection

from tornado.ioloop import IOLoop
from tornado.options import options
from tornado.netutil import bind_sockets, add_accept_handler
from threading import Thread

def run_server():
    ioloop = IOLoop.instance()
    sockets = bind_sockets(options.socket_port)
    for socket in sockets:
        add_accept_handler(socket, handle_connection, ioloop)
    server.listen(options.server_port)
    ioloop.start()

thread = Thread(target=run_server)
thread.setDaemon(True)
thread.start()
"""

def generate_wdb_server_script(options):
    path = os.path.join(options['server_root'], 'wdb-server.py')
    with open(path, 'w') as fp:
        print(WDB_SERVER_SCRIPT, file=fp)

WSGI_CONTROL_SCRIPT = """
#!/bin/sh

# %(sys_argv)s

HTTPD="%(httpd_executable)s %(httpd_arguments)s"

WSGI_RUN_USER="${WSGI_RUN_USER:-%(user)s}"
WSGI_RUN_GROUP="${WSGI_RUN_GROUP:-%(group)s}"

export WSGI_RUN_USER
export WSGI_RUN_GROUP

LANG='%(lang)s'
LC_ALL='%(locale)s'

export LANG
export LOCALE

ACMD="$1"
ARGV="$@"

if test -f %(server_root)s/envvars; then
    . %(server_root)s/envvars
fi

STATUSURL="http://%(host)s:%(port)s/server-status"

if [ "x$ARGV" = "x" ] ; then
    ARGV="-h"
fi

case $ACMD in
start|stop|restart|graceful|graceful-stop)
    exec $HTTPD -k $ARGV
    ;;
configtest)
    exec $HTTPD -t
    ;;
status)
    exec %(python_executable)s -m webbrowser -t $STATUSURL
    ;;
*)
    exec $HTTPD $ARGV
esac
"""

APACHE_ENVVARS_FILE = """
. %(envvars_script)s
"""

def generate_control_scripts(options):
    path = os.path.join(options['server_root'], 'apachectl')
    with open(path, 'w') as fp:
        print(WSGI_CONTROL_SCRIPT.lstrip() % options, file=fp)

    os.chmod(path, 0o755)

    path = os.path.join(options['server_root'], 'envvars')

    if options['envvars_script']:
        with open(path, 'w') as fp:
            if options['envvars_script']:
                print(APACHE_ENVVARS_FILE.lstrip() % options, file=fp)

    elif not os.path.isfile(path):
        with open(path, 'w') as fp:
            pass

def check_percentage(option, opt_str, value, parser):
    if value is not None and value < 0 or value > 1:
        raise optparse.OptionValueError('%s option value needs to be within '
                'the range 0 to 1.' % opt_str)
    setattr(parser.values, option.dest, value)

option_list = (
    optparse.make_option('--application-type', default='script',
            metavar='TYPE', help='The type of WSGI application entry point '
            'that was provided. Defaults to \'script\', indicating the '
            'traditional mod_wsgi style WSGI script file specified by a '
            'filesystem path. Alternatively one can supply \'module\', '
            'indicating that the provided entry point is a Python module '
            'which should be imported using the standard Python import '
            'mechanism, or \'paste\' indicating that the provided entry '
            'point is a Paste deployment configuration file.'),

    optparse.make_option('--host', default=None, metavar='IP-ADDRESS',
            help='The specific host (IP address) interface on which '
            'requests are to be accepted. Defaults to listening on '
            'all host interfaces.'),
    optparse.make_option('--port', default=8000, type='int',
            metavar='NUMBER', help='The specific port to bind to and '
            'on which requests are to be accepted. Defaults to port 8000.'),

    optparse.make_option('--ssl-port', type='int', metavar='NUMBER',
            help='The specific port to bind to and on which requests are '
            'to be accepted for SSL connections.'),
    optparse.make_option('--ssl-certificate', default=None,
            metavar='FILE-PATH', help='Specify the path to the SSL '
            'certificate files. It is expected that the files have \'.crt\' '
            'and \'.key\' extensions. This option should refer to the '
            'common part of the names for both files which appears before '
            'the extension.'),
    optparse.make_option('--https-only', action='store_true',
            default=False, help='Flag indicating whether any requests '
	    'made using a HTTP request over the non SSL connection should '
	    'be redirected automatically to use a HTTPS request over the '
	    'SSL connection.'),

    optparse.make_option('--server-name', default=None, metavar='HOSTNAME',
            help='The primary host name of the web server. If this name '
            'starts with \'www.\' then an automatic redirection from the '
            'parent domain name to the \'www.\' server name will created.'),
    optparse.make_option('--server-alias', action='append',
            dest='server_aliases', metavar='HOSTNAME', help='A secondary '
            'host name for the web server. May include wilcard patterns.'),
    optparse.make_option('--allow-localhost', action='store_true',
            default=False, help='Flag indicating whether access via '
            'localhost should still be allowed when a server name has been '
            'specified and a name based virtual host has been configured.'),

    optparse.make_option('--processes', type='int', metavar='NUMBER',
            help='The number of worker processes (instances of the WSGI '
            'application) to be started up and which will handle requests '
            'concurrently. Defaults to a single process.'),
    optparse.make_option('--threads', type='int', default=5, metavar='NUMBER',
            help='The number of threads in the request thread pool of '
            'each process for handling requests. Defaults to 5 in each '
            'process.'),

    optparse.make_option('--max-clients', type='int', default=None,
            metavar='NUMBER', help='The maximum number of simultaneous '
            'client connections that will be accepted. This will default '
            'to being 1.5 times the total number of threads in the '
            'request thread pools across all process handling requests.'),

    optparse.make_option('--initial-workers', type='float', default=None,
            metavar='NUMBER', action='callback', callback=check_percentage,
            help='The initial number of workers to create on startup '
            'expressed as a percentage of the maximum number of clients. '
            'The value provided should be between 0 and 1. The default is '
            'dependent on the type of MPM being used.'),
    optparse.make_option('--minimum-spare-workers', type='float',
            default=None, metavar='NUMBER', action='callback',
            callback=check_percentage, help='The minimum number of spare '
            'workers to maintain expressed as a percentage of the maximum '
            'number of clients. The value provided should be between 0 and '
            '1. The default is dependent on the type of MPM being used.'),
    optparse.make_option('--maximum-spare-workers', type='float',
            default=None, metavar='NUMBER', action='callback',
            callback=check_percentage, help='The maximum number of spare '
            'workers to maintain expressed as a percentage of the maximum '
            'number of clients. The value provided should be between 0 and '
            '1. The default is dependent on the type of MPM being used.'),

    optparse.make_option('--limit-request-body', type='int', default=10485760,
            metavar='NUMBER', help='The maximum number of bytes which are '
            'allowed in a request body. Defaults to 10485760 (10MB).'),

    optparse.make_option('--maximum-requests', type='int', default=0,
            metavar='NUMBER', help='The number of requests after which '
            'any one worker process will be restarted and the WSGI '
            'application reloaded. Defaults to 0, indicating that the '
            'worker process should never be restarted based on the number '
            'of requests received.'),

    optparse.make_option('--shutdown-timeout', type='int', default=5,
            metavar='SECONDS', help='Maximum number of seconds allowed '
            'to pass when waiting for a worker process to shutdown as a '
            'result of the maximum number of requests or inactivity timeout '
            'being reached, or when a user initiated SIGINT signal is sent '
            'to a worker process. When this timeout has been reached the '
            'worker process will be forced to exit even if there are '
            'still active requests or it is still running Python exit '
            'functions. Defaults to 5 seconds.'),

    optparse.make_option('--graceful-timeout', type='int', default=15,
            metavar='SECONDS', help='Grace period for requests to complete '
            'normally, without accepting new requests, when worker processes '
            'are being shutdown and restarted due to maximum requests being '
            'reached or due to graceful restart signal. Defaults to 15 '
            'seconds.'),

    optparse.make_option('--deadlock-timeout', type='int', default=60,
            metavar='SECONDS', help='Maximum number of seconds allowed '
            'to pass before the worker process is forcibly shutdown and '
            'restarted after a potential deadlock on the Python GIL has '
            'been detected. Defaults to 60 seconds.'),

    optparse.make_option('--inactivity-timeout', type='int', default=0,
            metavar='SECONDS', help='Maximum number of seconds allowed '
            'to pass before the worker process is shutdown and restarted '
            'when the worker process has entered an idle state and is no '
            'longer receiving new requests. Not enabled by default.'),

    optparse.make_option('--request-timeout', type='int', default=60,
            metavar='SECONDS', help='Maximum number of seconds allowed '
            'to pass before the worker process is forcibly shutdown and '
            'restarted when a request does not complete in the expected '
            'time. In a multi threaded worker, the request time is '
            'calculated as an average across all request threads. Defaults '
            'to 60 seconds.'),

    optparse.make_option('--connect-timeout', type='int', default=15,
            metavar='SECONDS', help='Maximum number of seconds allowed '
            'to pass before giving up on attempting to get a connection '
            'to the worker process from the Apache child process which '
            'accepted the request. This comes into play when the worker '
            'listener backlog limit is exceeded. Defaults to 15 seconds.'),

    optparse.make_option('--socket-timeout', type='int', default=60,
            metavar='SECONDS', help='Maximum number of seconds allowed '
            'to pass before timing out on a read or write operation on '
            'a socket and aborting the request. Defaults to 60 seconds.'),

    optparse.make_option('--queue-timeout', type='int', default=30,
            metavar='SECONDS', help='Maximum number of seconds allowed '
            'for a request to be accepted by a worker process to be '
            'handled, taken from the time when the Apache child process '
            'originally accepted the request. Defaults to 30 seconds.'),

    optparse.make_option('--server-backlog', type='int', default=500,
            metavar='NUMBER', help='Depth of server socket listener '
            'backlog for Apache child processes. Defaults to 500.'),

    optparse.make_option('--daemon-backlog', type='int', default=100,
            metavar='NUMBER', help='Depth of server socket listener '
            'backlog for daemon processes. Defaults to 100.'),

    optparse.make_option('--send-buffer-size', type='int', default=0,
            metavar='NUMBER', help='Size of socket buffer for sending '
            'data to daemon processes. Defaults to 0, indicating '
            'the system default socket buffer size is used.'),
    optparse.make_option('--receive-buffer-size', type='int', default=0,
            metavar='NUMBER', help='Size of socket buffer for receiving '
            'data from daemon processes. Defaults to 0, indicating '
            'the system default socket buffer size is used.'),
    optparse.make_option('--header-buffer-size', type='int', default=0,
            metavar='NUMBER', help='Size of buffer used for reading '
            'response headers from daemon processes. Defaults to 0, '
            'indicating internal default of 32768 bytes is used.'),

    optparse.make_option('--reload-on-changes', action='store_true',
            default=False, help='Flag indicating whether worker processes '
            'should be automatically restarted when any Python code file '
            'loaded by the WSGI application has been modified. Defaults to '
            'being disabled. When reloading on any code changes is disabled, '
            'the worker processes will still though be reloaded if the '
            'WSGI script file itself is modified.'),

    optparse.make_option('--user', default=default_run_user(), metavar='NAME',
            help='When being run by the root user, the user that the WSGI '
            'application should be run as.'),
    optparse.make_option('--group', default=default_run_group(),
            metavar='NAME', help='When being run by the root user, the group '
            'that the WSGI application should be run as.'),

    optparse.make_option('--callable-object', default='application',
            metavar='NAME', help='The name of the entry point for the WSGI '
            'application within the WSGI script file. Defaults to '
            'the name \'application\'.'),

    optparse.make_option('--map-head-to-get', default='Auto',
            metavar='OFF|ON|AUTO', help='Flag indicating whether HEAD '
            'requests should be mapped to a GET request. By default a HEAD '
            'request will be automatically mapped to a GET request when an '
            'Apache output filter is detected that may want to see the '
            'entire response in order to set up response headers correctly '
            'for a HEAD request. This can be disable by setting to \'Off\'.'),

    optparse.make_option('--document-root', metavar='DIRECTORY-PATH',
            help='The directory which should be used as the document root '
            'and which contains any static files.'),
    optparse.make_option('--directory-index', metavar='FILE-NAME',
            help='The name of a directory index resource to be found in the '
            'document root directory. Requests mapping to the directory '
            'will be mapped to this resource rather than being passed '
            'through to the WSGI application.'),

    optparse.make_option('--mount-point', metavar='URL-PATH', default='/',
            help='The URL path at which the WSGI application will be '
            'mounted. Defaults to being mounted at the root URL of the '
            'site.'),

    optparse.make_option('--url-alias', action='append', nargs=2,
            dest='url_aliases', metavar='URL-PATH FILE-PATH|DIRECTORY-PATH',
            help='Map a single static file or a directory of static files '
            'to a sub URL.'),
    optparse.make_option('--error-document', action='append', nargs=2,
            dest='error_documents', metavar='STATUS URL-PATH', help='Map '
            'a specific sub URL as the handler for HTTP errors generated '
            'by the web server.'),
    optparse.make_option('--error-override', action='store_true',
            default=False, help='Flag indicating whether Apache error '
            'documents will override application error responses.'),

    optparse.make_option('--keep-alive-timeout', type='int', default=0,
            metavar='SECONDS', help='The number of seconds which a client '
            'connection will be kept alive to allow subsequent requests '
            'to be made over the same connection. Defaults to 0, indicating '
            'that keep alive connections are disabled.'),

    optparse.make_option('--compress-responses', action='store_true',
            default=False, help='Flag indicating whether responses for '
            'common text based responses, such as plain text, HTML, XML, '
            'CSS and Javascript should be compressed.'),

    optparse.make_option('--server-metrics', action='store_true',
            default=False, help='Flag indicating whether internal server '
            'metrics will be available within the WSGI application. '
            'Defaults to being disabled.'),
    optparse.make_option('--server-status', action='store_true',
            default=False, help='Flag indicating whether web server status '
            'will be available at the /server-status sub URL. Defaults to '
            'being disabled.'),

    optparse.make_option('--auth-user-script', metavar='SCRIPT-PATH',
            default=None, help='Specify a Python script file for '
            'performing user authentication.'),
    optparse.make_option('--auth-type', metavar='TYPE',
            default='Basic', help='Specify the type of authentication '
            'scheme used when authenticating users. Defaults to using '
            '\'Basic\'. Alternate schemes available are \'Digest\'.'),

    optparse.make_option('--auth-group-script', metavar='SCRIPT-PATH',
            default=None, help='Specify a Python script file for '
            'performing group based authorization in conjunction with '
            'a user authentication script.'),
    optparse.make_option('--auth-group', metavar='SCRIPT-PATH',
            default='wsgi', help='Specify the group which users should '
            'be a member of when using a group based authorization script. '
            'Defaults to \'wsgi\' as a place holder but should be '
            'overridden to be the actual group you use rather than '
            'making your group name match the default.'),

    optparse.make_option('--include-file', action='append',
            dest='include_files', metavar='FILE-PATH', help='Specify the '
            'path to an additional web server configuration file to be '
            'included at the end of the generated web server configuration '
            'file.'),

    optparse.make_option('--envvars-script', metavar='FILE-PATH',
            help='Specify an alternate script file for user defined web '
            'server environment variables. Defaults to using the '
            '\'envvars\' stored under the server root directory.'),
    optparse.make_option('--lang', default='en_US.UTF-8', metavar='NAME',
            help='Specify the default language locale as normally defined '
            'by the LANG environment variable. Defaults to \'en_US.UTF-8\'.'),
    optparse.make_option('--locale', default='en_US.UTF-8', metavar='NAME',
            help='Specify the default natural language formatting style '
            'as normally defined by the LC_ALL environment variable. '
            'Defaults to \'en_US.UTF-8\'.'),

    optparse.make_option('--setenv', action='append', nargs=2,
            dest='setenv_variables', metavar='KEY VALUE', help='Specify '
            'a name/value pairs to be added to the per request WSGI environ '
            'dictionary'),
    optparse.make_option('--passenv', action='append',
            dest='passenv_variables', metavar='KEY', help='Specify the '
            'names of any process level environment variables which should '
            'be passed as a name/value pair in the per request WSGI '
            'environ dictionary.'),

    optparse.make_option('--working-directory', metavar='DIRECTORY-PATH',
            help='Specify the directory which should be used as the '
            'current working directory of the WSGI application. This '
            'directory will be searched when importing Python modules '
            'so long as the WSGI application doesn\'t subsequently '
            'change the current working directory. Defaults to the '
            'directory this script is run from.'),

    optparse.make_option('--pid-file', metavar='FILE-PATH',
            help='Specify an alternate file to be used to store the '
            'process ID for the root process of the web server.'),

    optparse.make_option('--server-root', metavar='DIRECTORY-PATH',
            help='Specify an alternate directory for where the generated '
            'web server configuration, startup files and logs will be '
            'stored. Defaults to a sub directory of /tmp.'),
    optparse.make_option('--log-directory', metavar='DIRECTORY-PATH',
            help='Specify an alternate directory for where the log files '
            'will be stored. Defaults to the server root directory.'),
    optparse.make_option('--log-level', default='info', metavar='NAME',
            help='Specify the log level for logging. Defaults to \'info\'.'),
    optparse.make_option('--access-log', action='store_true', default=False,
            help='Flag indicating whether the web server access log '
            'should be enabled. Defaults to being disabled.'),
    optparse.make_option('--startup-log', action='store_true', default=False,
            help='Flag indicating whether the web server startup log should '
            'be enabled. Defaults to being disabled.'),

    optparse.make_option('--rotate-logs', action='store_true', default=False,
            help='Flag indicating whether log rotation should be performed.'),
    optparse.make_option('--max-log-size', default=5, type='int',
            metavar='MB', help='The maximum size in MB the log file should '
            'be allowed to reach before log file rotation is performed.'),

    optparse.make_option('--rotatelogs-executable',
            default=apxs_config.ROTATELOGS, metavar='FILE-PATH',
            help='Override the path to the rotatelogs executable.'),

    optparse.make_option('--python-eggs', metavar='DIRECTORY-PATH',
            help='Specify an alternate directory which should be used for '
            'unpacking of Python eggs. Defaults to a sub directory of '
            'the server root directory.'),

    optparse.make_option('--httpd-executable', default=apxs_config.HTTPD,
            metavar='FILE-PATH', help='Override the path to the Apache web '
            'server executable.'),
    optparse.make_option('--modules-directory', default=apxs_config.LIBEXECDIR,
            metavar='DIRECTORY-PATH', help='Override the path to the Apache '
            'web server modules directory.'),
    optparse.make_option('--mime-types', default=find_mimetypes(),
            metavar='FILE-PATH', help='Override the path to the mime types '
            'file used by the web server.'),

    optparse.make_option('--with-newrelic', action='store_true',
            default=False, help='Flag indicating whether all New Relic '
            'performance monitoring features should be enabled.'),

    optparse.make_option('--with-newrelic-agent', action='store_true',
            default=False, help='Flag indicating whether the New Relic '
            'Python agent should be enabled for reporting application server '
            'metrics.'),
    optparse.make_option('--with-newrelic-platform', action='store_true',
            default=False, help='Flag indicating whether the New Relic '
            'platform plugin should be enabled for reporting server level '
            'metrics.'),

    optparse.make_option('--with-wdb', action='store_true', default=False,
            help='Flag indicating whether the wdb interactive debugger '
            'should be enabled for the WSGI application.'),

    optparse.make_option('--with-php5', action='store_true', default=False,
            help='Flag indicating whether PHP 5 support should be enabled.'),

    optparse.make_option('--enable-docs', action='store_true', default=False,
            help='Flag indicating whether the mod_wsgi documentation should '
            'be made available at the /__wsgi__/docs sub URL.'),

    optparse.make_option('--debug-mode', action='store_true', default=False,
            help='Flag indicating whether to run in single process mode '
            'to allow the running of an interactive Python debugger. This '
            'will override all options related to processes, threads and '
            'communication with workers. All forms of source code reloading '
            'will also be disabled. Both stdin and stdout will be attached '
            'to the console to allow interaction with the Python debugger.'),

    optparse.make_option('--setup-only', action='store_true', default=False,
            help='Flag indicating that after the configuration files have '
            'been setup, that the command should then exit and not go on '
            'to actually run up the Apache server. This is to allow for '
            'the generation of the configuration with Apache then later '
            'being started separately using the generated \'apachectl\' '
            'script.'),
)

def cmd_setup_server(params):
    formatter = optparse.IndentedHelpFormatter()
    formatter.set_long_opt_delimiter(' ')

    usage = '%prog setup-server script [options]'
    parser = optparse.OptionParser(usage=usage, option_list=option_list,
            formatter=formatter)

    (options, args) = parser.parse_args(params)

    _cmd_setup_server('setup-server', args, vars(options))

def _mpm_module_defines(modules_directory):
    result = []
    workers = ['event', 'worker', 'prefork']
    found = False
    for name in workers:
        if os.path.exists(os.path.join(modules_directory,
                'mod_mpm_%s.so' % name)):
            if not found:
                result.append('-DWSGI_MPM_ENABLE_%s_MODULE' % name.upper())
                found = True
            result.append('-DWSGI_MPM_EXISTS_%s_MODULE' % name.upper())
    return result

def _cmd_setup_server(command, args, options):
    options['sys_argv'] = repr(sys.argv)

    options['mod_wsgi_so'] = where()

    options['working_directory'] = options['working_directory'] or os.getcwd()

    if not options['host']:
        options['listener_host'] = None
        options['host'] = 'localhost'
    else:
        options['listener_host'] = options['host']

    options['process_name'] = '(wsgi:%s:%s:%s)' % (options['host'],
            options['port'], os.getuid())

    if not options['server_root']:
        options['server_root'] = '/tmp/mod_wsgi-%s:%s:%s' % (options['host'],
                options['port'], os.getuid())

    try:
        os.mkdir(options['server_root'])
    except Exception:
        pass

    if options['ssl_certificate']:
        options['ssl_certificate'] = os.path.abspath(
                options['ssl_certificate'])

    if not args:
        options['entry_point'] = os.path.join(options['server_root'],
                'default.wsgi')
        options['application_type'] = 'script'
        options['enable_docs'] = True
    elif options['application_type'] in ('script', 'paste'):
        options['entry_point'] = os.path.abspath(args[0])
    else:
        options['entry_point'] = args[0]

    if options['auth_user_script']:
        options['auth_user_script'] = os.path.abspath(
                options['auth_user_script'])

    if options['auth_group_script']:
        options['auth_group_script'] = os.path.abspath(
                options['auth_group_script'])

    options['documentation_directory'] = os.path.join(os.path.dirname(
            os.path.dirname(__file__)), 'docs')
    options['images_directory'] = os.path.join(os.path.dirname(
            os.path.dirname(__file__)), 'images')

    if os.path.exists(os.path.join(options['documentation_directory'],
            'index.html')):
        options['documentation_url'] = '/__wsgi__/docs/'
    else:
        options['documentation_url'] = 'http://www.modwsgi.org/'

    if not os.path.isabs(options['server_root']):
        options['server_root'] = os.path.abspath(options['server_root'])

    if not options['document_root']:
        options['document_root'] = os.path.join(options['server_root'],
                'htdocs')

    try:
        os.mkdir(options['document_root'])
    except Exception:
        pass

    if not options['mount_point'].startswith('/'):
        options['mount_point'] = os.path.normpath('/' + options['mount_point'])

    if options['mount_point'] != '/':
        parts = options['mount_point'].rstrip('/').split('/')[1:]
        subdir = options['document_root']
        try:
            for part in parts:
                subdir = os.path.join(subdir, part)
                if not os.path.exists(subdir):
                    os.mkdir(subdir)
        except Exception:
            raise

    if not os.path.isabs(options['document_root']):
        options['document_root'] = os.path.abspath(options['document_root'])

    if not options['log_directory']:
        options['log_directory'] = options['server_root']

    try:
        os.mkdir(options['log_directory'])
    except Exception:
        pass

    if not os.path.isabs(options['log_directory']):
        options['log_directory'] = os.path.abspath(options['log_directory'])

    options['error_log'] = os.path.join(options['log_directory'], 'error_log')

    options['pid_file'] = ((options['pid_file'] and os.path.abspath(
            options['pid_file'])) or os.path.join(options['server_root'],
            'httpd.pid'))

    options['python_eggs'] = (os.path.abspath(options['python_eggs']) if
            options['python_eggs'] is not None else None)

    if options['python_eggs'] is None:
        options['python_eggs'] = os.path.join(options['server_root'],
                'python-eggs')

    try:
        os.mkdir(options['python_eggs'])
    except Exception:
        pass

    options['multiprocess'] = options['processes'] is not None
    options['processes'] = options['processes'] or 1

    options['python_home'] = sys.prefix

    options['keep_alive'] = options['keep_alive_timeout'] != 0

    if options['server_metrics']:
        options['daemon_server_metrics_flag'] = 'On'
    else:
        options['daemon_server_metrics_flag'] = 'Off'

    if options['with_newrelic']:
        options['with_newrelic_agent'] = True
        options['with_newrelic_platform'] = True

    if options['with_newrelic_platform']:
        options['server_metrics'] = True

    generate_wsgi_handler_script(options)

    if options['with_newrelic_platform']:
        generate_server_metrics_script(options)

    if options['with_wdb']:
        generate_wdb_server_script(options)

    max_clients = options['processes'] * options['threads']

    if options['max_clients'] is not None:
        max_clients = max(options['max_clients'], max_clients)
    else:
        max_clients = int(1.5 * max_clients)

    initial_workers = options['initial_workers']
    min_spare_workers = options['minimum_spare_workers']
    max_spare_workers = options['maximum_spare_workers']

    if initial_workers is None:
        prefork_initial_workers = 0.02
    else:
        prefork_initial_workers = initial_workers

    if min_spare_workers is None:
        prefork_min_spare_workers = prefork_initial_workers
    else:
        prefork_min_spare_workers = min_spare_workers

    if max_spare_workers is None:
        prefork_max_spare_workers = 0.05
    else:
        prefork_max_spare_workers = max_spare_workers

    options['prefork_max_clients'] = max_clients
    options['prefork_server_limit'] = max_clients
    options['prefork_start_servers'] = max(1, int(
            prefork_initial_workers * max_clients))
    options['prefork_min_spare_servers'] = max(1, int(
            prefork_min_spare_workers * max_clients))
    options['prefork_max_spare_servers'] = max(1, int(
            prefork_max_spare_workers * max_clients))

    if initial_workers is None:
        worker_initial_workers = 0.2
    else:
        worker_initial_workers = initial_workers

    if min_spare_workers is None:
        worker_min_spare_workers = worker_initial_workers
    else:
        worker_min_spare_workers = min_spare_workers

    if max_spare_workers is None:
        worker_max_spare_workers = 0.6
    else:
        worker_max_spare_workers = max_spare_workers

    options['worker_max_clients'] = max_clients

    if max_clients > 25:
        options['worker_threads_per_child'] = int(max_clients /
                (int(max_clients / 25) + 1))
    else:
        options['worker_threads_per_child'] = max_clients

    options['worker_thread_limit'] = options['worker_threads_per_child']

    count = max_clients / options['worker_threads_per_child']
    options['worker_server_limit'] = int(math.floor(count))
    if options['worker_server_limit'] != count:
        options['worker_server_limit'] += 1

    options['worker_max_clients'] = (options['worker_server_limit'] *
            options['worker_threads_per_child'])

    options['worker_start_servers'] = max(1,
            int(worker_initial_workers * options['worker_server_limit']))
    options['worker_min_spare_threads'] = max(
            options['worker_threads_per_child'],
            int(worker_min_spare_workers * options['worker_server_limit']) *
            options['worker_threads_per_child'])
    options['worker_max_spare_threads'] = max(
            options['worker_threads_per_child'],
            int(worker_max_spare_workers * options['worker_server_limit']) *
            options['worker_threads_per_child'])

    options['httpd_conf'] = os.path.join(options['server_root'], 'httpd.conf')

    options['httpd_executable'] = os.environ.get('HTTPD',
            options['httpd_executable'])

    if not os.path.isabs(options['httpd_executable']):
         options['httpd_executable'] = find_program(
                 [options['httpd_executable']], 'httpd', ['/usr/sbin'])

    options['envvars_script'] = (os.path.abspath(
            options['envvars_script']) if options['envvars_script'] is
            not None else None)

    options['httpd_arguments_list'] = []

    if options['startup_log']:
        options['startup_log_filename']= os.path.join(
                options['log_directory'], 'startup.log')

        options['httpd_arguments_list'].append('-E')
        options['httpd_arguments_list'].append(
                options['startup_log_filename'])

    if options['server_name']:
        host = options['server_name']
    else:
        host = options['host']

    if options['port'] == 80:
        options['url'] = 'http://%s/' % host
    else:
        options['url'] = 'http://%s:%s/' % (host, options['port'])

    if options['ssl_port'] == 443:
        options['ssl_url'] = 'https://%s/' % host
    elif options['ssl_port'] is not None:
        options['ssl_url'] = 'https://%s:%s/' % (host, options['ssl_port'])
    else:
        options['ssl_url'] = None

    if options['debug_mode']:
        options['httpd_arguments_list'].append('-DONE_PROCESS')

    options['parent_domain'] = 'unspecified'

    if options['server_name']:
        options['httpd_arguments_list'].append('-DWSGI_VIRTUAL_HOST')
        if options['server_name'].lower().startswith('www.'):
            options['httpd_arguments_list'].append('-DWSGI_REDIRECT_WWW')
            options['parent_domain'] = options['server_name'][4:]

    if options['ssl_port'] and options['ssl_certificate']:
        options['httpd_arguments_list'].append('-DWSGI_WITH_SSL')
    if options['https_only']:
        options['httpd_arguments_list'].append('-DWSGI_HTTPS_ONLY')

    if options['server_aliases']:
        options['httpd_arguments_list'].append('-DWSGI_SERVER_ALIAS')
        options['server_aliases'] = ' '.join(options['server_aliases'])

    if options['allow_localhost']:
        options['httpd_arguments_list'].append('-DWSGI_ALLOW_LOCALHOST')

    if options['server_metrics']:
        options['httpd_arguments_list'].append('-DWSGI_SERVER_METRICS')
    if options['server_status']:
        options['httpd_arguments_list'].append('-DWSGI_SERVER_METRICS')
        options['httpd_arguments_list'].append('-DWSGI_SERVER_STATUS')
    if options['directory_index']:
        options['httpd_arguments_list'].append('-DWSGI_DIRECTORY_INDEX')
    if options['access_log']:
        options['httpd_arguments_list'].append('-DWSGI_ACCESS_LOG')
    if options['rotate_logs']:
        options['httpd_arguments_list'].append('-DWSGI_ROTATE_LOGS')
    if options['keep_alive'] != 0:
        options['httpd_arguments_list'].append('-DWSGI_KEEP_ALIVE')
    if options['compress_responses'] != 0:
        options['httpd_arguments_list'].append('-DWSGI_COMPRESS_RESPONSES')
    if options['multiprocess']:
        options['httpd_arguments_list'].append('-DWSGI_MULTIPROCESS')
    if options['listener_host']:
        options['httpd_arguments_list'].append('-DWSGI_LISTENER_HOST')
    if options['error_override']:
        options['httpd_arguments_list'].append('-DWSGI_ERROR_OVERRIDE')
    if options['auth_user_script']:
        options['httpd_arguments_list'].append('-DWSGI_AUTH_USER')
    if options['auth_group_script']:
        options['httpd_arguments_list'].append('-DWSGI_AUTH_GROUP')
    if options['with_php5']:
        options['httpd_arguments_list'].append('-DWSGI_WITH_PHP5')

    options['httpd_arguments_list'].extend(
            _mpm_module_defines(options['modules_directory']))

    options['httpd_arguments'] = '-f %s %s' % (options['httpd_conf'],
            ' '.join(options['httpd_arguments_list']))

    options['python_executable'] = sys.executable

    generate_apache_config(options)
    generate_control_scripts(options)

    print('Server URL        :', options['url'])

    if options['ssl_url']:
        print('Server URL (SSL)  :', options['ssl_url'])

    if options['server_status']:
        print('Server Status     :', '%sserver-status' % options['url'])

    print('Server Root       :', options['server_root'])
    print('Server Conf       :', options['httpd_conf'])

    print('Error Log File    :', options['error_log'])

    if options['access_log']:
        print('Access Log File   :', os.path.join(options['log_directory'],
                'access_log'))

    if options['envvars_script']:
        print('Environ Variables :', options['envvars_script'])

    if command == 'setup-server' or options['setup_only']:
        if not options['envvars_script']:
            print('Environ Variables :', options['server_root'] + '/envvars')
        print('Control Script    :', options['server_root'] + '/apachectl')

    return options

def cmd_start_server(params):
    formatter = optparse.IndentedHelpFormatter()
    formatter.set_long_opt_delimiter(' ')

    usage = '%prog start-server script [options]'
    parser = optparse.OptionParser(usage=usage, option_list=option_list,
            formatter=formatter)

    (options, args) = parser.parse_args(params)

    config = _cmd_setup_server('start-server', args, vars(options))

    if config['setup_only']:
        return

    executable = os.path.join(config['server_root'], 'apachectl')
    name = executable.ljust(len(config['process_name']))
    os.execl(executable, name, 'start', '-DNO_DETACH')

def cmd_install_module(params):
    formatter = optparse.IndentedHelpFormatter()
    formatter.set_long_opt_delimiter(' ')

    usage = '%prog install-module [options]'
    parser = optparse.OptionParser(usage=usage, formatter=formatter)

    parser.add_option('--modules-directory', metavar='DIRECTORY',
            default=apxs_config.LIBEXECDIR)

    (options, args) = parser.parse_args(params)

    if len(args) != 0:
        parser.error('Incorrect number of arguments.')

    target = os.path.abspath(os.path.join(options.modules_directory,
            MOD_WSGI_SO))

    shutil.copyfile(where(), target)

    print('LoadModule wsgi_module %s' % target)

def cmd_module_location(params):
    formatter = optparse.IndentedHelpFormatter()
    formatter.set_long_opt_delimiter(' ')

    usage = '%prog module-location'
    parser = optparse.OptionParser(usage=usage, formatter=formatter)

    (options, args) = parser.parse_args(params)

    if len(args) != 0:
        parser.error('Incorrect number of arguments.')

    print(where())

main_usage="""
%prog command [params]

Commands:
    install-module
    module-location
    setup-server
    start-server
"""

def main():
    parser = optparse.OptionParser(main_usage.strip())

    args = sys.argv[1:]

    if not args:
        parser.error('No command was specified.')

    command = args.pop(0)

    args = [os.path.expandvars(arg) for arg in args]

    if command == 'install-module':
        cmd_install_module(args)
    elif command == 'module-location':
        cmd_module_location(args)
    elif command == 'setup-server':
        cmd_setup_server(args)
    elif command == 'start-server':
        cmd_start_server(args)
    else:
        parser.error('Invalid command was specified.')

if __name__ == '__main__':
    main()
