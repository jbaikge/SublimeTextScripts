import gscommon as gs
import threading, Queue, traceback
import sublime

DOMAIN = 'GsQ'

class GsQ(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.sem = threading.Semaphore()
		self.view = None
		self.has_view = False
		self.msg = ''
		self.q = Queue.PriorityQueue()
		self.frame = 0
		self.frames = (
			u'\u25D2',
			u'\u25D1',
			u'\u25D3',
			u'\u25D0'
		)

	def run(self):
		while True:
			try:
				_, f, msg, view, has_view = self.q.get()
				if has_view:
					with self.sem:
						self.has_view = True
						self.view = view
						self.msg = ' %s: %s' % (DOMAIN, msg) if msg else ''

					self.animate()
					f()

					with self.sem:
						self.has_view = False
						self.view = None
						self.msg = ''
					sublime.set_timeout(lambda: view.set_status(DOMAIN, ''), 0)
				else:
					f()
			except Exception:
				gs.notice(DOMAIN, traceback.format_exc())

	def animate(self):
		with self.sem:
			if self.has_view:
				text = u'%s%s' % (self.frames[self.frame], self.msg)
				self.frame = (self.frame + 1) % len(self.frames)
			else:
				text = ''
				self.frame = 0

		def cb():
			with self.sem:
				if self.has_view:
					self.view.set_status(DOMAIN, text)
					sublime.set_timeout(self.animate, 250)
		sublime.set_timeout(cb, 0)

	def dispatch(self, f, msg, view=None, has_view=False, p=0):
		try:
			self.q.put((p, f, msg, view, has_view))
		except Exception:
			gs.notice(DOMAIN, traceback.format_exc())

Q = None

def dispatch(f, msg='', view=None, p=0):
	global Q
	if not Q:
		Q = GsQ()
		Q.start()
	if not view:
		win = sublime.active_window()
		if win:
			view = win.active_view()
	Q.dispatch(f, msg, view, view is not None, p)
