# coding: utf-8
"""
The MIT License (MIT)

Copyright (c) 2014 ywangd

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import console
import paramiko
import sys
import threading
from distutils.version import StrictVersion

try:
	import ui
except ImportError:
	import dummyui as ui

_SYS_STDOUT = sys.__stdout__
_stash = globals()['_stash']
""":type : StaSh"""

try:
	import pyte
except:
	console.show_activity('Installing pyte.....')
	_stash('pip install pyte==0.4.10')
	console.hide_activity()
finally:
	import pyte

if StrictVersion(paramiko.__version__) < StrictVersion('1.15'):
	# Install paramiko 1.16.0 to fix a bug with version < 1.15
	_stash('pip install paramiko==1.16.0')
	print('Please restart Pythonista for changes to take full effect')
	sys.exit(0)


class StashSSH(object):
	"""
	Wrapper class for paramiko client and pyte screen
	"""

	def __init__(self):
		self.close = False
		_stash.stashssh = self
		# Initialize the pyte screen based on the current screen size
		font = ('Menlo-Regular', _stash.config.getint('display',
								'TEXT_FONT_SIZE'))
		font_width, font_height = ui.measure_string('a', font=font)
		# noinspection PyUnresolvedReferences
		self.screen = pyte.screens.DiffScreen(
				int(_stash.ui.width / font_width),
				int(_stash.ui.height / font_height))
		self.stream = pyte.Stream()
		self.stream.attach(self.screen)
		try:
			self.client = _stash.csc_ssh
		except:
			raise Exception('Error')
		# self.client = paramiko.SSHClient()
		# self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

	def stdout_thread(self):
		while not self.close:
			if self.chan.recv_ready():
				rcv = self.chan.recv(4096)
				# _SYS_STDOUT.write('RRR {%s}\n' % repr(rcv))
				rcv = rcv.decode('utf-8', errors='ignore')
				x, y = self.screen.cursor.x, self.screen.cursor.y
				self.stream.feed(rcv)

				if (self.screen.dirty or
					x != self.screen.cursor.x or
					y != self.screen.cursor.y):
					self.update_screen()
					self.screen.dirty.clear()

				if self.chan.eof_received:
					break

	def update_screen(self):
		_stash.main_screen.load_pyte_screen(self.screen)
		_stash.renderer.render(no_wait=True)

	def single_exec(self, command):
		sin, sout, serr = self.client.exec_command(command)
		print(sout.read())
		print(serr.read())
		self.client.close()

	def interactive(self):
		self.chan = self.client.get_transport().open_session()
		self.chan.get_pty('linux', width=self.screen.columns,
					height=self.screen.lines)
		self.chan.invoke_shell()
		self.chan.set_combine_stderr(True)
		t1 = threading.Thread(target=self.stdout_thread)
		t1.start()
		t1.join()
		self.chan.close()
		self.client.close()
		print('\nconnection closed\n')


CTRL_KEY_FLAG = (1 << 18)


class SshUserActionDelegate(object):
	"""
	Substitute the default user actions delegates
	"""
	def __init__(self, ssh):
		self.ssh = ssh

	def send(self, s):
		while not self.ssh.chan.eof_received:
			if self.ssh.chan.send_ready():
				# _SYS_STDOUT.write('%s, [%s]' % (rng, replacement))
				self.ssh.chan.send(s.encode('utf-8'))
				break


class SshTvVkKcDelegate(SshUserActionDelegate):
	"""
	Delegate for TextView, Virtual keys and Key command
	"""
	def textview_did_begin_editing(self, tv):
		_stash.terminal.is_editing = True

	def textview_did_end_editing(self, tv):
		_stash.terminal.is_editing = False

	def textview_should_change(self, tv, rng, replacement):
		self.send(replacement or '\x08')  # delete
		return False  # always false

	def textview_did_change(self, tv):
		pass

	def textview_did_change_selection(self, tv):
		pass

	def kc_pressed(self, key, modifierFlags):
		if modifierFlags == CTRL_KEY_FLAG:
			keys = {'A': '\x01', 'C': '\x03', 'D': '\x04', 'E': '\x05',
				'K': '\x0B', 'L': '\x0C', 'U': '\x15', 'Z': '\x1A',
				'[': '\x1B'}  # [ == ESC
			c = keys.get(key, '')
			if c:
				self.send(c)
		elif modifierFlags == 0:
			keys = {'UIKeyInputUpArrow': '\x10',
				'UIKeyInputDownArrow': '\x0E',
				'UIKeyInputLeftArrow': '\033[D',
				'UIKeyInputRightArrow': '\033[C'}
			c = keys.get(key, '')
			if c:
				self.send(c)

	def vk_tapped(self, vk):
		if vk.name == 'k_tab':
			self.send('\t')
		elif vk.name == 'k_CC':
			self.kc_pressed('C', CTRL_KEY_FLAG)
		elif vk.name == 'k_CD':
			self.kc_pressed('D', CTRL_KEY_FLAG)
		elif vk.name == 'k_CU':
			self.kc_pressed('U', CTRL_KEY_FLAG)
		elif vk.name == 'k_CZ':
			self.kc_pressed('Z', CTRL_KEY_FLAG)
		elif vk.name == 'k_hup':
			self.kc_pressed('UIKeyInputUpArrow', 0)
		elif vk.name == 'k_hdn':
			self.kc_pressed('UIKeyInputDownArrow', 0)

		elif vk.name == 'k_KB':
			if _stash.terminal.is_editing:
				_stash.terminal.end_editing()
			else:
				_stash.terminal.begin_editing()


class SshSVDelegate(SshUserActionDelegate):
	"""
	Delegate for scroll view
	"""
	SCROLL_PER_CHAR = 20.0  # Number of pixels to scroll to move 1 character

	def scrollview_did_scroll(self, scrollview):
		# integrate small scroll motions, but keep scrollview from actually moving
		if not scrollview.decelerating:
			scrollview.superview.dx -= (scrollview.content_offset[0] /
							SshSVDelegate.SCROLL_PER_CHAR)
		scrollview.content_offset = (0.0, 0.0)

		offset = int(scrollview.superview.dx)
		if offset:
			scrollview.superview.dx -= offset
			self.send('\033[C' if offset > 0 else '\033[D')


if __name__ == '__main__':
	ssh = StashSSH()
	tv_vk_kc_delegate = SshTvVkKcDelegate(ssh)
	sv_delegate = SshSVDelegate(ssh)

	_stash.csc_send = sv_delegate.send

	_stash.stream.feed(u'\u009bc', render_it=False)
	with _stash.user_action_proxy.config(tv_responder=tv_vk_kc_delegate,
						kc_responder=tv_vk_kc_delegate.kc_pressed,
						vk_responder=tv_vk_kc_delegate.vk_tapped,
						sv_responder=sv_delegate):
		ssh.interactive()
