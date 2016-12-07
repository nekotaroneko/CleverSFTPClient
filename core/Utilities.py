#!/usr/bin/env python
#coding: utf-8

import socket
import threading
import console
import os,sys
import paramiko
from stat import S_ISDIR
import time
import objc_util
import ui
import logging

					
		
def get_table_list(table):
	new_list1 = []
	new_list = []
	for row in table.selected_rows:
		new_list1.append(table.delegate._items[row[1]])
		
	for _item in table.data_source.items:
		if _item in new_list1:
			new_list.append(_item)
	new_list = remove_repeated_word(new_list)
	_new_list = [x for x in new_list if not x == ".."]
	return _new_list
	
def remove_repeated_word(seq):
	seen = set()
	seen_add = seen.add
	return [ x for x in seq if x not in seen and not seen_add(x)]
	
def to_abs_path(*value):
	import os
	abs_path = os.path.join(os.path.expanduser('~'),'Documents')
	for _value in value:
		abs_path = os.path.join(abs_path,_value)
	return abs_path
	
def to_relpath(path):
	relpath = os.path.relpath(path, to_abs_path())
	return relpath
	
def human_size(size_bytes, no_suffixs=False):
	'''Helper function for formatting human-readable file sizes'''
	if size_bytes == 1:
		return "1 byte"
	suffixes_table = [('bytes',0),('KB',0),('MB',1),('GB',2),('TB',2), ('PB',2)]
	num = float(size_bytes)
	for suffix, precision in suffixes_table:
		if num < 1024.0:
			break
		num /= 1024.0
	if precision == 0:
		formatted_size = "%d" % num
	else:
		formatted_size = str(round(num, ndigits=precision))
	if not no_suffixs:
		return "%s %s" % (formatted_size, suffix)
	else:
		return formatted_size
		
def rmtree(sftp, remotepath, level=0):
	import posixpath,stat
	for f in sftp.listdir_attr(remotepath):
		rpath = posixpath.join(remotepath, f.filename)
		if stat.S_ISDIR(f.st_mode):
			rmtree(sftp, rpath, level=(level + 1))
		else:
			rpath = posixpath.join(remotepath, f.filename)
			#print('removing %s%s' % ('    ' * level, rpath))
			sftp.remove(rpath)
	#print('removing %s%s' % ('    ' * level, remotepath))
	sftp.rmdir(remotepath)


class SSHSession(object):
	def __init__(self,hostname,username='root',key_file=None,password=None):
		self.ssh = ssh = paramiko.SSHClient()  # will create the object
		ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())# no known_hosts error
		
		if key_file is not None:
			key=open(key_file,'r')
			try:
				pkey=paramiko.RSAKey.from_private_key(key, password=password)
			except paramiko.SSHException as e:
				if e.message == 'not a valid RSA private key file':
					
					pkey=paramiko.DSSKey.from_private_key(key, password=password)
				else:
					raise e
			
			ssh.connect(hostname, username=username, password=password, pkey=pkey, timeout=5)#key_filename=key_file)
		else:
			if password is not None:
				ssh.connect(hostname, username=username, password=password,timeout=5)
			else: raise Exception('Must supply either key_file or password')
			
		self.sftp = self.ssh.open_sftp()
	
	def close(self):
		self.ssh.close()
		self.sftp.close()
		
	def command(self,cmd):
		stdin,stdout,stderr = self.ssh.exec_command('{}\n'.format(cmd))
	

			
		for line in stderr:
			
			raise Exception(line)
		
		
	def put(self,localfile,remotefile,sftp_callback=None):
		#  Copy localfile to remotefile, overwriting or creating as needed.
		self.sftp.put(localfile,remotefile,sftp_callback)
		
	def put_all(self,localpath,remotepath,progress=None):
		#  recursively upload a full directory
		os.chdir(os.path.split(localpath)[0])
		parent=os.path.split(localpath)[1]
		for walker in os.walk(parent):
			try:
				self.sftp.mkdir(os.path.join(remotepath,walker[0]))
			except:
				pass
			for file in walker[2]:
				if progress:
					sftp_callback = progress(file, os.path.join(remotepath,walker[0],file), 'put', open_path=os.path.join(walker[0],file))
					
				else:
					sftp_callback = None
				self.put(os.path.join(walker[0],file),os.path.join(remotepath,walker[0],file),sftp_callback)
				
	def get(self,remotefile,localfile,sftp_callback=None):
		#  Copy remotefile to localfile, overwriting or creating as needed.
		self.sftp.get(remotefile,localfile,sftp_callback)
		
	def sftp_walk(self,remotepath):
		# Kindof a stripped down  version of os.walk, implemented for
		# sftp.  Tried running it flat without the yields, but it really
		# chokes on big directories.
		path=remotepath
		files=[]
		folders=[]
		for f in self.sftp.listdir_attr(remotepath):
			if S_ISDIR(f.st_mode):
				folders.append(f.filename)
			else:
				files.append(f.filename)
		#print (path,folders,files)
		yield path,folders,files
		for folder in folders:
			new_path=os.path.join(remotepath,folder)
			for x in self.sftp_walk(new_path):
				yield x
				
	def get_all(self,remotepath,localpath, progress=None):
		#  recursively download a full directory
		#  Harder than it sounded at first, since paramiko won't walk
		#
		# For the record, something like this would gennerally be faster:
		# ssh user@host 'tar -cz /source/folder' | tar -xz
		
		self.sftp.chdir(os.path.split(remotepath)[0])
		parent=os.path.split(remotepath)[1]
		try:
			os.mkdir(localpath)
		except:
			pass
		for walker in self.sftp_walk(parent):
			try:
				os.mkdir(os.path.join(localpath,walker[0]))
			except:
				pass
			for file in walker[2]:
				if progress:
					sftp_callback = progress(os.path.join(walker[0],file), file, 'get', open_path=os.path.join(localpath,walker[0],file))
				else:
					sftp_callback = None
				self.get(os.path.join(walker[0],file),os.path.join(localpath,walker[0],file),sftp_callback)
				
	def write_command(self,text,remotefile):
		#  Writes text to remotefile, and makes remotefile executable.
		#  This is perhaps a bit niche, but I was thinking I needed it.
		#  For the record, I was incorrect.
		self.sftp.open(remotefile,'w').write(text)
		self.sftp.chmod(remotefile,755)

def wait_tab_closed(tab_name):
	rootVC = objc_util.UIApplication.sharedApplication().keyWindow().rootViewController()
	tabVC = rootVC.detailViewController()
	
	while True:
		try:
			time.sleep(1)
			
			tab_title_list = [ x.title() for x in tabVC.tabViewControllers()]
			web_count = len([ x for x in tab_title_list if str(x)==tab_name])
			if web_count == 0:
				break
		except KeyboardInterrupt:
			console.hud_alert("When finish editing file, close current tab",'',5)
			
			

		
def stash_installer():
	try:
		from stash.stash import StaSh
	except:
		console.show_activity('Installing stash.....')
		import requests
		exec(requests.get('http://bit.ly/get-stash').text,globals(), locals())
		console.hide_activity()
	finally:
		from stash.stash import StaSh
		ssh_path = to_abs_path('site-packages', 'stash', '.ssh')
		if not os.path.isdir(ssh_path):
			os.makedirs(ssh_path)
			
