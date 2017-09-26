import datetime

class Loggable(object):
	@classmethod
	def log(cls, message):
		print "[%s][%s] %s\n" % (datetime.datetime.now(), cls.__name__, message)

	@classmethod
	def log_error(cls, message):
		print "[%s][%s] ERROR: %s\n" % (datetime.datetime.now(), cls.__name__, message)
