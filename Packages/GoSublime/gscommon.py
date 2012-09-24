# Sublime modelines - https://github.com/SublimeText/Modelines
# sublime: translate_tabs_to_spaces false; rulers [100,120]

import sublime
import subprocess, re, os, threading, tempfile, datetime, uuid, traceback as tbck
from subprocess import Popen, PIPE

try:
	STARTUP_INFO = subprocess.STARTUPINFO()
	STARTUP_INFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
	STARTUP_INFO.wShowWindow = subprocess.SW_HIDE
except (AttributeError):
	STARTUP_INFO = None

_sem = threading.Semaphore()
_settings = {
	"env": {},
	"gscomplete_enabled": False,
	"gocode_cmd": "",
	"fmt_enabled": False,
	"fmt_tab_indent": True,
	"fmt_tab_width": 8,
	"gslint_enabled": False,
	"comp_lint_enabled": False,
	"comp_lint_commands": [],
	"gslint_timeout": 0,
	"autocomplete_snippets": False,
	"autocomplete_tests": False,
	"margo_cmd": [],
	"margo_addr": "",
	"on_save": [],
	"shell": [],
	"default_snippets": [],
	"snippets": [],
	"gsbundle_enabled": False,
}

NAME = 'GoSublime'

CLASS_PREFIXES = {
	'const': u'\u0196',
	'func': u'\u0192',
	'type': u'\u0288',
	'var':  u'\u03BD',
	'package': u'package \u03C1',
}

NAME_PREFIXES = {
	'interface': u'\u00A1',
}

GOARCHES = [
	'386',
	'amd64',
	'arm',
]

GOOSES = [
	'darwin',
	'freebsd',
	'linux',
	'netbsd',
	'openbsd',
	'plan9',
	'windows',
	'unix',
]

GOOSARCHES = []
for s in GOOSES:
	for arch in GOARCHES:
		GOOSARCHES.append('%s_%s' % (s, arch))

GOOSARCHES_PAT = re.compile(r'^(.+?)(?:_(%s))?(?:_(%s))?\.go$' % ('|'.join(GOOSES), '|'.join(GOARCHES)))

IGNORED_SCOPES = frozenset([
	'string.quoted.double.go',
	'string.quoted.single.go',
	'string.quoted.raw.go',
	'comment.line.double-slash.go',
	'comment.block.go'
])

def apath(fn, cwd=None):
	if not os.path.isabs(fn):
		if not cwd:
			cwd = os.getcwd()
		fn = os.path.join(cwd, fn)
	return os.path.normcase(os.path.normpath(fn))

def temp_dir(subdir=''):
	tmpdir = os.path.join(tempfile.gettempdir(), NAME, subdir)
	err = ''
	try:
		os.makedirs(tmpdir)
	except Exception as ex:
		err = str(ex)
	return (tmpdir, err)

def temp_file(suffix='', prefix='', delete=True):
	try:
		f = tempfile.NamedTemporaryFile(suffix=suffix, prefix=prefix, dir=temp_dir(), delete=delete)
	except Exception as ex:
		return (None, 'Error: %s' % ex)
	return (f, '')

def basedir_or_cwd(fn):
	if fn and not fn.startswith('view://'):
		return os.path.dirname(fn)
	return os.getcwd()

def popen(args, stdout=PIPE, stderr=PIPE, shell=False, environ={}, cwd=None, bufsize=0):
	ev = os.environ.copy()
	ev.update(env())
	ev.update(environ)

	try:
		setsid = os.setsid
	except Exception:
		setsid = None

	return Popen(args, stdout=stdout, stderr=stderr, stdin=PIPE, startupinfo=STARTUP_INFO,
		shell=shell, env=ev, cwd=cwd, preexec_fn=setsid, bufsize=bufsize)

def runcmd(args, input=None, stdout=PIPE, stderr=PIPE, shell=False, environ={}, cwd=None):
	out = ""
	err = ""
	exc = None

	try:
		p = popen(args, stdout=stdout, stderr=stderr, shell=shell, environ=environ, cwd=cwd)
		if input is not None:
			input = input.encode('utf-8')
		out, err = p.communicate(input=input)
		out = out.decode('utf-8') if out else ''
		err = err.decode('utf-8') if err else ''
	except (Exception) as e:
		err = u'Error while running %s: %s' % (args[0], e)
		exc = e

	return (out, err, exc)

def is_a(v, base):
	return isinstance(v, type(base))

def is_a_string(v):
	return isinstance(v, basestring)

def settings_obj():
	return sublime.load_settings("GoSublime.sublime-settings")

def setting(key, default=None):
	with _sem:
		return _settings.get(key, default)

def println(*a):
	print('\n** %s **:' % datetime.datetime.now())
	for s in a:
		print(str(s).strip())
	print('--------------------------------')

debug = println

def notice(domain, txt):
	txt = "%s: %s" % (domain, txt)
	println(txt)
	status_message(txt)

def notice_undo(domain, txt, view, should_undo):
	def cb():
		if should_undo:
			view.run_command('undo')
		notice(domain, txt)
	sublime.set_timeout(cb, 0)

def show_output(domain, s, print_output=True, syntax_file='', replace=True, merge_domain=False, scroll_end=False):
	def cb(domain, s, print_output, win):
		panel_name = '%s-output' % domain
		if merge_domain:
			s = '%s: %s' % (domain, s)
			if print_output:
				println(s)
		elif print_output:
			println('%s: %s' % (domain, s))

		win = sublime.active_window()
		if win:
			panel = win.get_output_panel(panel_name)
			edit = panel.begin_edit()
			panel.set_read_only(False)

			try:
				if replace:
					panel.replace(edit, sublime.Region(0, panel.size()), s)
				else:
					panel.insert(edit, panel.size(), s+'\n')
			finally:
				panel.end_edit(edit)

			panel.sel().clear()
			pst = panel.settings()
			pst.set("rulers", [])
			pst.set("fold_buttons", True)
			pst.set("fade_fold_buttons", False)
			pst.set("gutter", False)
			pst.set("line_numbers", False)
			if syntax_file:
				if syntax_file == 'GsDoc':
					panel.set_syntax_file('Packages/GoSublime/GsDoc.tmLanguage')
					panel.run_command("fold_by_level", { "level": 1 })
				else:
					panel.set_syntax_file(syntax_file)
			panel.set_read_only(True)
			win.run_command("show_panel", {"panel": "output.%s" % panel_name})
			if scroll_end:
				panel.show(panel.size())
	sublime.set_timeout(lambda: cb(domain, s, print_output, syntax_file), 0)

def is_pkg_view(view=None):
	# todo implement this fully
	return is_go_source_view(view, False)

def is_go_source_view(view=None, strict=True):
	if view is None:
		return False

	selector_match = view.score_selector(view.sel()[0].begin(), 'source.go') > 0
	if selector_match:
		return True

	if strict:
		return False

	fn = view.file_name() or ''
	return fn.lower().endswith('.go')

def active_valid_go_view(win=None, strict=True):
	if not win:
		win = sublime.active_window()
	if win:
		view = win.active_view()
		if view and is_go_source_view(view, strict):
			return view
	return None

def rowcol(view):
	return view.rowcol(view.sel()[0].begin())

def os_is_windows():
	return os.name == "nt"

def getenv(name, default=''):
	return env().get(name, default)

def env():
	"""
	Assamble environment information needed for correct operation. In particular,
	ensure that directories containing binaries are included in PATH.
	"""
	e = os.environ.copy()
	e.update(setting('env', {}))
	roots = e.get('GOPATH', '').split(os.pathsep)
	roots.append(e.get('GOROOT', ''))

	# For custom values of GOPATH, installed binaries via go install
	# will go into the "bin" dir of the corresponding GOPATH path.
	# Therefore, make sure these paths are included in PATH.
	add_path = e.get('PATH', '').split(os.pathsep)
	for s in roots:
		if s:
			s = os.path.join(s, 'bin')
			if s not in add_path:
				add_path.append(s)

	if os_is_windows():
		l = ['C:\\Go\\bin']
	else:
		l = ['/usr/local/go/bin', '/usr/bin']

	for s in l:
		if s not in add_path:
			add_path.append(s)

	e['PATH'] = os.pathsep.join(add_path)

	# Ensure no unicode objects leak through. The reason is twofold:
	# 	* On Windows, Python 2.6 (used by Sublime Text) subprocess.Popen
	# 	  can only take bytestrings as environment variables in the
	#	  "env"	parameter. Reference:
	# 	  https://github.com/DisposaBoy/GoSublime/issues/112
	# 	  http://stackoverflow.com/q/12253014/1670
	#   * Avoids issues with networking too.
	for k, v in e.iteritems():
		try:
			e[k] = str(v)
		except Exception as ex:
			println('%s: Bad env: %s' % (NAME, ex))

	return e

def sync_settings():
	global _settings
	so = settings_obj()
	with _sem:
		for k in _settings:
			v = so.get(k, None)
			if v is not None:
				# todo: check the type of `v`
				_settings[k] = v

		e = _settings.get('env', {})
		vfn = ''
		win = sublime.active_window()
		if win:
			view = win.active_view()
			if view:
				vfn = view.file_name()
				psettings = view.settings().get(NAME)
				if psettings:
					for k in _settings:
						v = psettings.get(k, None)
						if v is not None and k != "env":
							_settings[k] = v
					penv = psettings.get('env')
					if penv:
						e.update(penv)

		vfn = basedir_or_cwd(vfn)
		comps = vfn.split(os.sep)
		gs_gopath = []
		for i, s in enumerate(comps):
			if s.lower() == "src":
				gs_gopath.append(os.sep.join(comps[:i]))
		gs_gopath.reverse()
		gs_gopath = str(os.pathsep.join(gs_gopath))

		for k in e:
			e[k] = e[k].replace('$GS_GOPATH', gs_gopath)
		for k in e:
			e[k] = str(os.path.expandvars(os.path.expanduser(e[k])))

		_settings['env'] = e

def view_fn(view):
	if view is not None:
		if view.file_name():
			return view.file_name()
		return 'view://%s' % view.id()
	return ''

def view_src(view):
	if view:
		return view.substr(sublime.Region(0, view.size()))
	return ''

def win_view(vfn=None, win=None):
	if not win:
		win = sublime.active_window()

	view = None
	if win:
		if not vfn or vfn == "<stdin>":
			view = win.active_view()
		elif vfn.startswith("view://"):
			try:
				vid = int(vfn[7:])
				for v in win.views():
					if v.id() == vid:
						view = v
						break
			except:
				pass
		else:
			view = win.open_file(vfn)
	return (win, view)

def do_focus(fn, row, col, win=None, focus_pkg=True):
	win, view = win_view(fn, win)
	if win is None or view is None:
		notice(NAME, 'Cannot find file position %s:%s:%s' % (fn, row, col))
	elif view.is_loading():
		focus(fn, row, col, win, focus_pkg)
	else:
		win.focus_view(view)
		if row <= 0 and col <= 0 and focus_pkg:
			r = view.find('^package ', 0)
			if r:
				row, col = view.rowcol(r.begin())
		view.run_command("gs_goto_row_col", { "row": row, "col": col })

def focus(fn, row=0, col=0, win=None, timeout=100, focus_pkg=True):
	sublime.set_timeout(lambda: do_focus(fn, row, col, win, focus_pkg), timeout)

def sm_cb():
	global sm_text
	global sm_set_text
	global sm_frame

	with sm_lck:
		ntasks = len(sm_tasks)
		tm = sm_tm
		s = sm_text
		if s:
			delta = (datetime.datetime.now() - tm)
			if delta.seconds >= 5:
				sm_text = ''

	if ntasks > 0:
		if s:
			s = u'%s, %s' % (sm_frames[sm_frame], s)
		else:
			s = u'%s' % sm_frames[sm_frame]

		if ntasks > 1:
			s = '%d %s' % (ntasks, s)

		sm_frame = (sm_frame + 1) % len(sm_frames)

	if s != sm_set_text:
		sm_set_text = s
		st2_status_message(s)

	sched_sm_cb()


def sched_sm_cb():
	sublime.set_timeout(sm_cb, 250)

def status_message(s):
	global sm_text
	global sm_tm

	with sm_lck:
		sm_text = s
		sm_tm = datetime.datetime.now()

def begin(domain, message, set_status=True, cancel=None):
	if message and set_status:
		status_message('%s: %s' % (domain, message))

	id = uuid.uuid4()
	dat = {
		'start': datetime.datetime.now(),
		'domain': domain,
		'message': message,
		'cancel': cancel,
	}

	with sm_lck:
		sm_tasks[id] = dat

	return id

def end(task_id):
	with sm_lck:
		try:
			del(sm_tasks[task_id])
		except:
			pass

def task(task_id, default=None):
	with sm_lck:
		return sm_tasks.get(task_id, default)

def clear_tasks():
	with sm_lck:
		sm_tasks = {}

def show_quick_panel(items, cb=None):
	def f():
		win = sublime.active_window()
		if win:
			win.show_quick_panel(items, (lambda i: cb(i, win)) if cb else (lambda i: None))
	sublime.set_timeout(f, 0)

def go_env_goroot():
	out, _, _ = runcmd(['go env GOROOT'], shell=True)
	return out.strip().encode('utf-8')

def list_dir_tree(dirname, filter, exclude_prefix=('.', '_')):
	lst = []

	try:
		for fn in os.listdir(dirname):
			if fn[0] in exclude_prefix:
				continue

			basename = fn.lower()
			fn = os.path.join(dirname, fn)

			if os.path.isdir(fn):
				lst.extend(list_dir_tree(fn, filter))
			else:
				if filter:
					pathname = fn.lower()
					_, ext = os.path.splitext(basename)
					ext = ext.lstrip('.')
					if filter(pathname, basename, ext):
						lst.append(fn)
				else:
					lst.append(fn)
	except Exception:
		pass

	return lst

def traceback(domain='GoSublime'):
	return '%s: %s' % (domain, tbck.format_exc())

def show_traceback(domain):
	show_output(domain, traceback(), replace=False, merge_domain=False)

def ustr(s):
	if isinstance(s, unicode):
		return s
	return str(s).decode('utf-8')

def astr(s):
	if isinstance(s, unicode):
		return s.encode('utf-8')
	return str(s)

try:
	st2_status_message
except:
	sm_lck = threading.Lock()
	sm_tasks = {}
	sm_frame = 0
	sm_frames = (
		u'\u25D2',
		u'\u25D1',
		u'\u25D3',
		u'\u25D0'
	)
	sm_tm = datetime.datetime.now()
	sm_text = ''
	sm_set_text = ''

	st2_status_message = sublime.status_message
	sublime.status_message = status_message

	sched_sm_cb()

# init
settings_obj().clear_on_change("GoSublime.settings")
settings_obj().add_on_change("GoSublime.settings", sync_settings)
sync_settings()
