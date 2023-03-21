#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>
# Copyright: (c) 2017, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['stableinterface'],
                    'supported_by': 'core'}

DOCUMENTATION = r'''
---
module: deploy
version_added: historical
short_description: Copy files to remote locations

'''

EXAMPLES = r'''
- name: Copy file with owner and permissions
  copy:
    src: /srv/myfiles/foo.conf
    dest: /etc/foo.conf
    owner: foo
    group: foo
    mode: '0644'

- name: Copy file with owner and permission, using symbolic representation
  copy:
    src: /srv/myfiles/foo.conf
    dest: /etc/foo.conf
    owner: foo
    group: foo
    mode: u=rw,g=r,o=r

- name: Another symbolic mode example, adding some permissions and removing others
  copy:
    src: /srv/myfiles/foo.conf
    dest: /etc/foo.conf
    owner: foo
    group: foo
    mode: u+rw,g-wx,o-rwx

- name: Copy a new "ntp.conf file into place, backing up the original if it differs from the copied version
  copy:
    src: /mine/ntp.conf
    dest: /etc/ntp.conf
    owner: root
    group: root
    mode: '0644'
    backup: yes

- name: Copy a new "sudoers" file into place, after passing validation with visudo
  copy:
    src: /mine/sudoers
    dest: /etc/sudoers
    validate: /usr/sbin/visudo -csf %s

- name: Copy a "sudoers" file on the remote machine for editing
  copy:
    src: /etc/sudoers
    dest: /etc/sudoers.edit
    remote_src: yes
    validate: /usr/sbin/visudo -csf %s

- name: Copy using inline content
  copy:
    content: '# This file was moved to /etc/other.conf'
    dest: /etc/mine.conf

- name: If follow=yes, /path/to/file will be overwritten by contents of foo.conf
  copy:
    src: /etc/foo.conf
    dest: /path/to/link  # link to /path/to/file
    follow: yes

- name: If follow=no, /path/to/link will become a file and be overwritten by contents of foo.conf
  copy:
    src: /etc/foo.conf
    dest: /path/to/link  # link to /path/to/file
    follow: no
'''

RETURN = r'''
dest:
    description: Destination file/path
    returned: success
    type: str
    sample: /path/to/file.txt
src:
    description: Source file used for the copy on the target machine
    returned: changed
    type: str
    sample: /home/httpd/.ansible/tmp/ansible-tmp-1423796390.97-147729857856000/source
md5sum:
    description: MD5 checksum of the file after running copy
    returned: when supported
    type: str
    sample: 2a5aeecc61dc98c4d780b14b330e3282
checksum:
    description: SHA1 checksum of the file after running copy
    returned: success
    type: str
    sample: 6e642bb8dd5c2e027bf21dd923337cbb4214f827
backup_file:
    description: Name of backup file created
    returned: changed and if backup=yes
    type: str
    sample: /path/to/file.txt.2015-02-12@22:09~
gid:
    description: Group id of the file, after execution
    returned: success
    type: int
    sample: 100
group:
    description: Group of the file, after execution
    returned: success
    type: str
    sample: httpd
owner:
    description: Owner of the file, after execution
    returned: success
    type: str
    sample: httpd
uid:
    description: Owner id of the file, after execution
    returned: success
    type: int
    sample: 100
mode:
    description: Permissions of the target, after execution
    returned: success
    type: str
    sample: 0644
size:
    description: Size of the target, after execution
    returned: success
    type: int
    sample: 1220
state:
    description: State of the target, after execution
    returned: success
    type: str
    sample: file
'''

import errno
import filecmp
import grp
import os
import os.path
import platform
import pwd
import shutil
import stat
import tempfile
import traceback

from inspect import currentframe, getframeinfo

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.process import get_bin_path
from ansible.module_utils._text import to_bytes, to_native
from ansible.module_utils.six import PY3


# The AnsibleModule object
module = None


class AnsibleModuleError(Exception):
    def __init__(self, results):
        self.results = results


# Once we get run_command moved into common, we can move this into a common/files module.  We can't
# until then because of the module.run_command() method.  We may need to move it into
# basic::AnsibleModule() until then but if so, make it a private function so that we don't have to
# keep it for backwards compatibility later.
def clear_facls(path):
    setfacl = get_bin_path('setfacl', True)
    # FIXME "setfacl -b" is available on Linux and FreeBSD. There is "setfacl -D e" on z/OS. Others?
    acl_command = [setfacl, '-b', path]
    b_acl_command = [to_bytes(x) for x in acl_command]
    rc, out, err = module.run_command(b_acl_command, environ_update=dict(LANG='C', LC_ALL='C', LC_MESSAGES='C'))
    if rc != 0:
        raise RuntimeError('Error running "{0}": stdout: "{1}"; stderr: "{2}"'.format(' '.join(b_acl_command), out, err))


def split_pre_existing_dir(dirname):
    '''
    Return the first pre-existing directory and a list of the new directories that will be created.
    '''
    head, tail = os.path.split(dirname)
    b_head = to_bytes(head, errors='surrogate_or_strict')
    if head == '':
        return ('.', [tail])
    if not os.path.exists(b_head):
        if head == '/':
            raise AnsibleModuleError(results={'msg': "The '/' directory doesn't exist on this machine."})
        (pre_existing_dir, new_directory_list) = split_pre_existing_dir(head)
    else:
        return (head, [tail])
    new_directory_list.append(tail)
    return (pre_existing_dir, new_directory_list)


def adjust_recursive_directory_permissions(pre_existing_dir, new_directory_list, module, directory_args, changed):
    '''
    Walk the new directories list and make sure that permissions are as we would expect
    '''

    if new_directory_list:
        working_dir = os.path.join(pre_existing_dir, new_directory_list.pop(0))
        directory_args['path'] = working_dir
        changed = module.set_fs_attributes_if_different(directory_args, changed)
        changed = adjust_recursive_directory_permissions(working_dir, new_directory_list, module, directory_args, changed)
    return changed


def chown_recursive(path, module):
    changed = False
    owner = module.params['owner']
    group = module.params['group']

    if owner is not None:
        if not module.check_mode:
            for dirpath, dirnames, filenames in os.walk(path):
                owner_changed = module.set_owner_if_different(dirpath, owner, False)
                if owner_changed is True:
                    changed = owner_changed
                for dir in [os.path.join(dirpath, d) for d in dirnames]:
                    owner_changed = module.set_owner_if_different(dir, owner, False)
                    if owner_changed is True:
                        changed = owner_changed
                for file in [os.path.join(dirpath, f) for f in filenames]:
                    owner_changed = module.set_owner_if_different(file, owner, False)
                    if owner_changed is True:
                        changed = owner_changed
        else:
            uid = pwd.getpwnam(owner).pw_uid
            for dirpath, dirnames, filenames in os.walk(path):
                owner_changed = (os.stat(dirpath).st_uid != uid)
                if owner_changed is True:
                    changed = owner_changed
                for dir in [os.path.join(dirpath, d) for d in dirnames]:
                    owner_changed = (os.stat(dir).st_uid != uid)
                    if owner_changed is True:
                        changed = owner_changed
                for file in [os.path.join(dirpath, f) for f in filenames]:
                    owner_changed = (os.stat(file).st_uid != uid)
                    if owner_changed is True:
                        changed = owner_changed
    if group is not None:
        if not module.check_mode:
            for dirpath, dirnames, filenames in os.walk(path):
                group_changed = module.set_group_if_different(dirpath, group, False)
                if group_changed is True:
                    changed = group_changed
                for dir in [os.path.join(dirpath, d) for d in dirnames]:
                    group_changed = module.set_group_if_different(dir, group, False)
                    if group_changed is True:
                        changed = group_changed
                for file in [os.path.join(dirpath, f) for f in filenames]:
                    group_changed = module.set_group_if_different(file, group, False)
                    if group_changed is True:
                        changed = group_changed
        else:
            gid = grp.getgrnam(group).gr_gid
            for dirpath, dirnames, filenames in os.walk(path):
                group_changed = (os.stat(dirpath).st_gid != gid)
                if group_changed is True:
                    changed = group_changed
                for dir in [os.path.join(dirpath, d) for d in dirnames]:
                    group_changed = (os.stat(dir).st_gid != gid)
                    if group_changed is True:
                        changed = group_changed
                for file in [os.path.join(dirpath, f) for f in filenames]:
                    group_changed = (os.stat(file).st_gid != gid)
                    if group_changed is True:
                        changed = group_changed

    return changed


def copy_diff_files(src, dest, module):
    changed = False
    owner = module.params['owner']
    group = module.params['group']
    local_follow = module.params['local_follow']
    backup = module.params['backup']
    diff_files = filecmp.dircmp(src, dest).diff_files
    print('check here (copy_diff_files)',getframeinfo(currentframe()).lineno)
    print('src', '-', src, '| dest - ', dest)
    print('diff_files', '-'*8, diff_files, ' len - ',len(diff_files))
    if len(diff_files):
        changed = True
    if not module.check_mode:
        for item in diff_files:
            src_item_path = os.path.join(src, item)
            dest_item_path = os.path.join(dest, item)
            b_src_item_path = to_bytes(src_item_path, errors='surrogate_or_strict')
            b_dest_item_path = to_bytes(dest_item_path, errors='surrogate_or_strict')
            print('check here (copy_diff_files loop)',getframeinfo(currentframe()).lineno)
            print('b_src_item_path :', b_src_item_path)
            print('b_dest_item_path :', b_dest_item_path)
            if os.path.islink(b_src_item_path) and local_follow is False:
                linkto = os.readlink(b_src_item_path)
                os.symlink(linkto, b_dest_item_path)
            else:
                if backup: # and module.params['backup_dir']:
                    check_remote_files(b_dest_item_path, module)
                    if os.path.exists(b_dest_item_path):
                        backup_file = backup_local(b_dest_item_path, module)
                        print('check here (backup_file)',getframeinfo(currentframe()).lineno, 'backup_file ',backup_file)
                shutil.copy2(b_src_item_path, b_dest_item_path)

            if owner is not None:
                module.set_owner_if_different(b_dest_item_path, owner, False)
            if group is not None:
                module.set_group_if_different(b_dest_item_path, group, False)
            changed = True
    return changed


def copy_left_only(src, dest, module):
    changed = False
    owner = module.params['owner']
    group = module.params['group']
    local_follow = module.params['local_follow']
    backup = module.params['backup']
    left_only = filecmp.dircmp(src, dest).left_only
    print('check here (copy_left_only)',getframeinfo(currentframe()).lineno)
    print('src', '-', src, '| dest - ', dest)
    print('left_only', '-'*8, left_only, ' len - ', len(left_only))
    if len(left_only):
        changed = True
    if not module.check_mode:
        for item in left_only:
            src_item_path = os.path.join(src, item)
            dest_item_path = os.path.join(dest, item)
            b_src_item_path = to_bytes(src_item_path, errors='surrogate_or_strict')
            b_dest_item_path = to_bytes(dest_item_path, errors='surrogate_or_strict')
            print('check here (left_only loop)',getframeinfo(currentframe()).lineno)
            print('b_src_item_path :', b_src_item_path)
            print('b_dest_item_path :', b_dest_item_path)

            # If src item is linked dir and symlink follow is yes
            if os.path.islink(b_src_item_path) and os.path.isdir(b_src_item_path) and local_follow is True:
                if backup: # and module.params['backup_dir']:
                    check_remote_files(b_dest_item_path, module)
                    if os.path.exists(b_dest_item_path):
                        backup_file = module.backup_local(b_dest_item_path)
                shutil.copytree(b_src_item_path, b_dest_item_path, symlinks=not(local_follow))
                chown_recursive(b_dest_item_path, module)

            # If src item is linked dir and symlink follow is no
            if os.path.islink(b_src_item_path) and os.path.isdir(b_src_item_path) and local_follow is False:
                linkto = os.readlink(b_src_item_path)
                os.symlink(linkto, b_dest_item_path)

            # If src item is linked file and symlink follow is yes
            if os.path.islink(b_src_item_path) and os.path.isfile(b_src_item_path) and local_follow is True:
                if backup: # and module.params['backup_dir']:
                    check_remote_files(b_dest_item_path, module)
                    if os.path.exists(b_dest_item_path):
                        backup_file = module.backup_local(b_dest_item_path)
                shutil.copy2(b_src_item_path, b_dest_item_path)
                if owner is not None:
                    module.set_owner_if_different(b_dest_item_path, owner, False)
                if group is not None:
                    module.set_group_if_different(b_dest_item_path, group, False)

            # If src item is linked file and symlink follow is no
            if os.path.islink(b_src_item_path) and os.path.isfile(b_src_item_path) and local_follow is False:
                linkto = os.readlink(b_src_item_path)
                os.symlink(linkto, b_dest_item_path)
            
            # Copy if src item is file
            if not os.path.islink(b_src_item_path) and os.path.isfile(b_src_item_path):
                print('check here (left_only loop)',getframeinfo(currentframe()).lineno, 'copying ',b_src_item_path)
                if backup: # and module.params['backup_dir']:
                    check_remote_files(b_dest_item_path, module)
                    if os.path.exists(b_dest_item_path):
                        backup_file = module.backup_local(b_dest_item_path)
                        print('check here (backup_file)',getframeinfo(currentframe()).lineno, 'backup_file ',backup_file)
                shutil.copy2(b_src_item_path, b_dest_item_path)
                if owner is not None:
                    module.set_owner_if_different(b_dest_item_path, owner, False)
                if group is not None:
                    module.set_group_if_different(b_dest_item_path, group, False)

            # Copy if src item is directory
            if not os.path.islink(b_src_item_path) and os.path.isdir(b_src_item_path):
                if backup: # and module.params['backup_dir']:
                    check_remote_files(b_dest_item_path, module)
                shutil.copytree(b_src_item_path, b_dest_item_path, symlinks=not(local_follow))
                chown_recursive(b_dest_item_path, module)

            changed = True
    return changed


def copy_common_dirs(src, dest, module):
    changed = False
    common_dirs = filecmp.dircmp(src, dest).common_dirs
    print('check here (copy_common_dirs)',getframeinfo(currentframe()).lineno)
    print('src', '-', src, '| dest - ', dest)
    print('common_dirs', '-'*8, common_dirs)
    for item in common_dirs:
        src_item_path = os.path.join(src, item)
        dest_item_path = os.path.join(dest, item)
        b_src_item_path = to_bytes(src_item_path, errors='surrogate_or_strict')
        b_dest_item_path = to_bytes(dest_item_path, errors='surrogate_or_strict')
        diff_files_changed = copy_diff_files(b_src_item_path, b_dest_item_path, module)
        left_only_changed = copy_left_only(b_src_item_path, b_dest_item_path, module)
        if diff_files_changed or left_only_changed:
            changed = True

        # recurse into subdirectory
        changed = changed or copy_common_dirs(os.path.join(src, item), os.path.join(dest, item), module)
    return changed

def backup_local(fn, module):
    '''make a date-marked backup of the specified file, return True or False on success or failure'''

    backupdest = ''
    dest = module.params['dest']
    #backup_dir = module.params['backup_dir']
    backup_date = module.params['_backup_date']
    #ticket_id = module.params['ticket_id']
    backup_dir = '/app/bak'
    ticket_id = '123456'
    
    b_dest = to_bytes(dest, errors='surrogate_or_strict')
    b_backup_dir = to_bytes(backup_dir, errors='surrogate_or_strict')
    b_backup_date = to_bytes(backup_date, errors='surrogate_or_strict')
    b_ticket_id = to_bytes(ticket_id, errors='surrogate_or_strict')
    
    if os.path.exists(fn):
        backupdest = os.path.join(b_backup_dir, b_backup_date, b_ticket_id)
        print('check here backupdest: ', backupdest, getframeinfo(currentframe()).lineno)
        print('check here fn: ', fn, getframeinfo(currentframe()).lineno)
        
        backupdest = os.path.join(backup_dir, backup_date, ticket_id, fn.replace(dest, '', 1))
        
        if PY3:
            try:
                os.makedirs(os.path.dirname(backupdest), exist_ok=True)
            except:
                pass
        else:
            try:
                os.makedirs(os.path.dirname(backupdest))
            except:
                pass
        print('check here backupdest: ', backupdest, getframeinfo(currentframe()).lineno)

        try:
            module.preserved_copy( fn, backupdest)
        except (shutil.Error, IOError) as e:
            module.fail_json(msg='Could not make backup of %s to %s: %s' % (fn, backupdest, to_native(e)))

    return backupdest


def check_remote_files(path, module):
    ''' Backup remote files before copying.'''
    print('check here',getframeinfo(currentframe()).lineno)
    print('-' * 8)
    for dirpath, dirnames, filenames in os.walk(path):
        print('dirpath', dirpath)
        print('dirnames', dirnames)
        print('filenames', filenames)
        print('-' * 8)

def main():

    global module

    module = AnsibleModule(
        # not checking because of daisy chain to file module
        argument_spec=dict(
            src=dict(type='path'),
            _original_basename=dict(type='str'),  # used to handle 'dest is a directory' via template, a slight hack
            content=dict(type='str', no_log=True),
            dest=dict(type='path', required=True),
            backup=dict(type='bool', default=False),
            backup_dir=dict(type='path'),
            ticket_id=dict(type='str'),
            force=dict(type='bool', default=True, aliases=['thirsty']),
            validate=dict(type='str'),
            directory_mode=dict(type='raw'),
            remote_src=dict(type='bool'),
            local_follow=dict(type='bool'),
            checksum=dict(type='str'),
            follow=dict(type='bool', default=False),
            _backup_date=dict(type='str'),
        ),
        add_file_common_args=True,
        supports_check_mode=True,
    )
    import time
    module.params['_backup_date'] = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(time.time()))
    if module.params.get('thirsty'):
        module.deprecate('The alias "thirsty" has been deprecated and will be removed, use "force" instead', version='2.13')

    src = module.params['src']
    b_src = to_bytes(src, errors='surrogate_or_strict')
    dest = module.params['dest']
    # Make sure we always have a directory component for later processing
    if os.path.sep not in dest:
        dest = '.{0}{1}'.format(os.path.sep, dest)
    b_dest = to_bytes(dest, errors='surrogate_or_strict')
    backup = module.params['backup']
    force = module.params['force']
    _original_basename = module.params.get('_original_basename', None)
    validate = module.params.get('validate', None)
    follow = module.params['follow']
    local_follow = module.params['local_follow']
    mode = module.params['mode']
    owner = module.params['owner']
    group = module.params['group']
    remote_src = module.params['remote_src']
    checksum = module.params['checksum']
    
    

    if not os.path.exists(b_src):
        module.fail_json(msg="Source %s not found" % (src))
    if not os.access(b_src, os.R_OK):
        module.fail_json(msg="Source %s not readable" % (src))

    # Preserve is usually handled in the action plugin but mode + remote_src has to be done on the
    # remote host
    if module.params['mode'] == 'preserve':
        module.params['mode'] = '0%03o' % stat.S_IMODE(os.stat(b_src).st_mode)
    mode = module.params['mode']

    checksum_dest = None

    if os.path.isfile(src):
        checksum_src = module.sha1(src)
    else:
        checksum_src = None

    # Backwards compat only.  This will be None in FIPS mode
    try:
        if os.path.isfile(src):
            md5sum_src = module.md5(src)
        else:
            md5sum_src = None
    except ValueError:
        md5sum_src = None

    changed = False

    if checksum and checksum_src != checksum:
        module.fail_json(
            msg='Copied file does not match the expected checksum. Transfer failed.',
            checksum=checksum_src,
            expected_checksum=checksum
        )

    #print('check here',getframeinfo(currentframe()).lineno)
    
    # Special handling for recursive copy - create intermediate dirs
    if dest.endswith(os.sep):
        if _original_basename:
            dest = os.path.join(dest, _original_basename)
        b_dest = to_bytes(dest, errors='surrogate_or_strict')
        dirname = os.path.dirname(dest)
        b_dirname = to_bytes(dirname, errors='surrogate_or_strict')
        if not os.path.exists(b_dirname):
            try:
                (pre_existing_dir, new_directory_list) = split_pre_existing_dir(dirname)
            except AnsibleModuleError as e:
                e.result['msg'] += ' Could not copy to {0}'.format(dest)
                module.fail_json(**e.results)

            os.makedirs(b_dirname)
            directory_args = module.load_file_common_arguments(module.params)
            directory_mode = module.params["directory_mode"]
            if directory_mode is not None:
                directory_args['mode'] = directory_mode
            else:
                directory_args['mode'] = None
            adjust_recursive_directory_permissions(pre_existing_dir, new_directory_list, module, directory_args, changed)

    if os.path.isdir(b_dest):
        basename = os.path.basename(src)
        if _original_basename:
            basename = _original_basename
        dest = os.path.join(dest, basename)
        b_dest = to_bytes(dest, errors='surrogate_or_strict')

    print('check here',getframeinfo(currentframe()).lineno)
    print('b_dest----', b_dest)
    print('b_dest exists ----', os.path.exists(b_dest))
    if os.path.exists(b_dest):
        if os.path.islink(b_dest) and follow:
            b_dest = os.path.realpath(b_dest)
            dest = to_native(b_dest, errors='surrogate_or_strict')
        if not force:
            module.exit_json(msg="file already exists", src=src, dest=dest, changed=False)
        if os.access(b_dest, os.R_OK) and os.path.isfile(b_dest):
            checksum_dest = module.sha1(dest)
    else:
        print('check here (dest not exists)',getframeinfo(currentframe()).lineno)
        print('b_dest----', b_dest)
        print('b_dest dirname ----', os.path.dirname(b_dest))
        print('b_dest dirname ----', os.path.exists(os.path.dirname(b_dest)))
        #os.makedirs(b_dest)
        if not os.path.exists(os.path.dirname(b_dest)):
            try:
                # os.path.exists() can return false in some
                # circumstances where the directory does not have
                # the execute bit for the current user set, in
                # which case the stat() call will raise an OSError
                os.stat(os.path.dirname(b_dest))
            except OSError as e:
                if "permission denied" in to_native(e).lower():
                    module.fail_json(msg="Destination directory %s is not accessible" % (os.path.dirname(dest)))
            module.fail_json(msg="Destination directory %s does not exist" % (os.path.dirname(dest)))

    if not os.access(os.path.dirname(b_dest), os.W_OK) and not module.params['unsafe_writes']:
        module.fail_json(msg="Destination %s not writable" % (os.path.dirname(dest)))

    backup_file = None
    if checksum_src != checksum_dest or os.path.islink(b_dest):
        if not module.check_mode:
            try:
                if backup:
                    if os.path.exists(b_dest):
                        backup_file = module.backup_local(dest)
                # allow for conversion from symlink.
                if os.path.islink(b_dest):
                    os.unlink(b_dest)
                    open(b_dest, 'w').close()
                if validate:
                    # if we have a mode, make sure we set it on the temporary
                    # file source as some validations may require it
                    if mode is not None:
                        module.set_mode_if_different(src, mode, False)
                    if owner is not None:
                        module.set_owner_if_different(src, owner, False)
                    if group is not None:
                        module.set_group_if_different(src, group, False)
                    if "%s" not in validate:
                        module.fail_json(msg="validate must contain %%s: %s" % (validate))
                    (rc, out, err) = module.run_command(validate % src)
                    if rc != 0:
                        module.fail_json(msg="failed to validate", exit_status=rc, stdout=out, stderr=err)
                b_mysrc = b_src
                if remote_src and os.path.isfile(b_src):
                    _, b_mysrc = tempfile.mkstemp(dir=os.path.dirname(b_dest))

                    shutil.copyfile(b_src, b_mysrc)
                    try:
                        shutil.copystat(b_src, b_mysrc)
                    except OSError as err:
                        if err.errno == errno.ENOSYS and mode == "preserve":
                            module.warn("Unable to copy stats {0}".format(to_native(b_src)))
                        else:
                            raise

                # might be needed below
                if PY3 and hasattr(os, 'listxattr'):
                    try:
                        src_has_acls = 'system.posix_acl_access' in os.listxattr(src)
                    except Exception as e:
                        # assume unwanted ACLs by default
                        src_has_acls = True

                module.atomic_move(b_mysrc, dest, unsafe_writes=module.params['unsafe_writes'])

                if PY3 and hasattr(os, 'listxattr') and platform.system() == 'Linux' and not remote_src:
                    # atomic_move used above to copy src into dest might, in some cases,
                    # use shutil.copy2 which in turn uses shutil.copystat.
                    # Since Python 3.3, shutil.copystat copies file extended attributes:
                    # https://docs.python.org/3/library/shutil.html#shutil.copystat
                    # os.listxattr (along with others) was added to handle the operation.

                    # This means that on Python 3 we are copying the extended attributes which includes
                    # the ACLs on some systems - further limited to Linux as the documentation above claims
                    # that the extended attributes are copied only on Linux. Also, os.listxattr is only
                    # available on Linux.

                    # If not remote_src, then the file was copied from the controller. In that
                    # case, any filesystem ACLs are artifacts of the copy rather than preservation
                    # of existing attributes. Get rid of them:

                    if src_has_acls:
                        # FIXME If dest has any default ACLs, there are not applied to src now because
                        # they were overridden by copystat. Should/can we do anything about this?
                        # 'system.posix_acl_default' in os.listxattr(os.path.dirname(b_dest))

                        try:
                            clear_facls(dest)
                        except ValueError as e:
                            if 'setfacl' in to_native(e):
                                # No setfacl so we're okay.  The controller couldn't have set a facl
                                # without the setfacl command
                                pass
                            else:
                                raise
                        except RuntimeError as e:
                            # setfacl failed.
                            if 'Operation not supported' in to_native(e):
                                # The file system does not support ACLs.
                                pass
                            else:
                                raise

            except (IOError, OSError):
                module.fail_json(msg="failed to copy: %s to %s" % (src, dest), traceback=traceback.format_exc())
        changed = True
    else:
        changed = False

    print('check here',getframeinfo(currentframe()).lineno)
    print('remote_src ', '-'*8, remote_src)
    if checksum_src is None and checksum_dest is None:
        #print(getframeinfo(currentframe()).lineno)
        if remote_src and os.path.isdir(module.params['src']):
            b_src = to_bytes(module.params['src'], errors='surrogate_or_strict')
            b_dest = to_bytes(module.params['dest'], errors='surrogate_or_strict')
            print('check here',getframeinfo(currentframe()).lineno)
            print('b_src','-'*8, b_src)
            print('b_dest','-'*8, b_dest)

            if src.endswith(os.path.sep) and os.path.isdir(module.params['dest']):
                print('check here',getframeinfo(currentframe()).lineno)
                diff_files_changed = copy_diff_files(b_src, b_dest, module)
                left_only_changed = copy_left_only(b_src, b_dest, module)
                common_dirs_changed = copy_common_dirs(b_src, b_dest, module)
                owner_group_changed = chown_recursive(b_dest, module)
                if diff_files_changed or left_only_changed or common_dirs_changed or owner_group_changed:
                    changed = True

            if src.endswith(os.path.sep) and not os.path.exists(module.params['dest']):
                print('check here (src ends with / dest not exists)',getframeinfo(currentframe()).lineno)
                b_basename = to_bytes(os.path.basename(src), errors='surrogate_or_strict')
                b_dest = to_bytes(os.path.join(b_dest, b_basename), errors='surrogate_or_strict')
                b_src = to_bytes(os.path.join(module.params['src'], ""), errors='surrogate_or_strict')
                if not module.check_mode:
                    if backup and module.params['backup_dir']:
                        check_remote_files(src, module)
                    shutil.copytree(b_src, b_dest, symlinks=not(local_follow))
                chown_recursive(dest, module)
                changed = True

            if not src.endswith(os.path.sep) and os.path.isdir(module.params['dest']):
                print('check here (dest is dir)',getframeinfo(currentframe()).lineno)
                b_basename = to_bytes(os.path.basename(src), errors='surrogate_or_strict')
                b_dest = to_bytes(os.path.join(b_dest, b_basename), errors='surrogate_or_strict')
                b_src = to_bytes(os.path.join(module.params['src'], ""), errors='surrogate_or_strict')
                if not module.check_mode and not os.path.exists(b_dest):
                    print('check here (dest not exists)',getframeinfo(currentframe()).lineno)
                    #if backup: # and module.params['backup_dir']:
                    #    check_remote_files(src, module)
                    shutil.copytree(b_src, b_dest, symlinks=not(local_follow))
                    changed = True
                    chown_recursive(dest, module)
                if module.check_mode and not os.path.exists(b_dest):
                    changed = True
                if os.path.exists(b_dest):
                    print('check here (dest exists)',getframeinfo(currentframe()).lineno)                    
                    diff_files_changed = copy_diff_files(b_src, b_dest, module)
                    left_only_changed = copy_left_only(b_src, b_dest, module)
                    common_dirs_changed = copy_common_dirs(b_src, b_dest, module)
                    owner_group_changed = chown_recursive(b_dest, module)
                    if diff_files_changed or left_only_changed or common_dirs_changed or owner_group_changed:
                        changed = True

            print('check here ',getframeinfo(currentframe()).lineno, '    |  ', src.endswith(os.path.sep), os.path.exists(module.params['dest']))
            if not src.endswith(os.path.sep) and not os.path.exists(module.params['dest']):
                print('check here (dest not exists)',getframeinfo(currentframe()).lineno)
                b_basename = to_bytes(os.path.basename(module.params['src']), errors='surrogate_or_strict')
                b_dest = to_bytes(os.path.join(b_dest, b_basename), errors='surrogate_or_strict')
                if not module.check_mode and not os.path.exists(b_dest):
                    print('check here (dest not exists)',getframeinfo(currentframe()).lineno)
                    os.makedirs(b_dest)
                    b_src = to_bytes(os.path.join(module.params['src'], ""), errors='surrogate_or_strict')
                    diff_files_changed = copy_diff_files(b_src, b_dest, module)
                    left_only_changed = copy_left_only(b_src, b_dest, module)
                    common_dirs_changed = copy_common_dirs(b_src, b_dest, module)
                    owner_group_changed = chown_recursive(b_dest, module)
                    if diff_files_changed or left_only_changed or common_dirs_changed or owner_group_changed:
                        changed = True
                if module.check_mode and not os.path.exists(b_dest):
                    changed = True

    res_args = dict(
        dest=dest, src=src, md5sum=md5sum_src, checksum=checksum_src, changed=changed
    )
    if backup_file:
        res_args['backup_file'] = backup_file

    module.params['dest'] = dest
    if not module.check_mode:
        file_args = module.load_file_common_arguments(module.params)
        res_args['changed'] = module.set_fs_attributes_if_different(file_args, res_args['changed'])

    module.exit_json(**res_args)


if __name__ == '__main__':
    main()
