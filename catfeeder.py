import base64
import time
import datetime

import tweepy
from twitter.oauth import OAuth
from twitter.api import Twitter
import os

try:
	import RPi.GPIO as GPIO
except ImportError as e:
	print e
	class GPIO(object):
		OUT = "out"
		IN = "in"
		BCM = "bcm"

		@classmethod
		def setmode(cls, mode):
			print "%s.setmode('%s')" % (cls.__name__, mode)

		@classmethod
		def setup(cls, pin, mode):
			print "%s.setup(%s, '%s')" % (cls.__name__, pin, mode)

		@classmethod
		def output(cls, pin, value):
			print "%s.output('%s', %s)" % (cls.__name__, pin, value)

		@classmethod
		def input(cls, pin):
			return 0

		@classmethod
		def cleanup(cls):
			print "%s.cleanup()" % cls.__name__

SLEEP_INTERVAL = 0.1


class Loggable(object):
	@classmethod
	def log(cls, message):
		print "[%s][%s] %s\n" % (datetime.datetime.now(), cls.__name__, message)

class Camera(Loggable):
	@classmethod
	def capture(self):
		filename = "/home/pi/webcam/%s.jpg" % datetime.datetime.now()
		os.system('fswebcam "%s"' % filename)
		return filename

class PinManager(Loggable):
	MODE_OUT = GPIO.OUT
	MODE_IN = GPIO.IN

	@classmethod
	def initalize(cls):
		cls.log('initializing')
		GPIO.setmode(GPIO.BCM)

	@classmethod
	def setup_pin(cls, pin, mode):
		cls.log('setup pin %s, %s' % (pin, mode))
		GPIO.setup(pin, mode)

	@classmethod
	def write_pin(cls, pin, value):
		cls.log("write_pin('%s', %s)" % (pin, value))
		GPIO.output(pin, value)
	
	@classmethod
	def read_pin(cls, pin):
		value = GPIO.input(pin)
		print "Read Pin(%s) = %s" % (pin, value)
		return True if value else False

	@classmethod
	def cleanup(cls):
		cls.log('cleanup')
		GPIO.cleanup()

class TickerTickTooManyError(Exception):
	pass

class TickerIncrementedEvent(Exception):
	def __init__(self, remaining):
		self.ticks_remaining = remaining
		super(TickerIncrementedEvent, self).__init__("Ticks remaining: %s" % remaining)

class TickerCounter(Loggable):
	TICKER_PIN = 5

	def __init__(self):
		self.ticks_remaining = 0
		PinManager.setup_pin(self.TICKER_PIN, GPIO.IN)
		self.activated = self.read_state()

	def read_state(self):
		return PinManager.read_pin(self.TICKER_PIN)

	def update(self):
		ticker_activated = self.read_state()
		if self.activated:
			if not ticker_activated:
				self.on_ticker_deactivated()
		else:
			if ticker_activated:
				self.on_ticker_activated()

	def on_ticker_activated(self):
		self.activated = True
		self.log("ticker activated")

	def on_ticker_deactivated(self):
		self.activated = False
		self.log("ticker deactivated")
		self.increment_ticker()
		raise TickerIncrementedEvent(self.ticks_remaining) #communicate the tick

	def increment_ticker(self):
		if self.ticks_remaining == 0:
			raise TickerTickTooManyError()

		self.ticks_remaining = self.ticks_remaining - 1
		self.log("Tick! Remaining: %s" % self.ticks_remaining)

	def count_from(self, ticks):
		self.ticks_remaining = ticks

class FeedSchedule(Loggable):
	def __init__(self, hour, minute, second, duration):
		self.hour = hour
		self.minute = minute
		self.second = second
		self.duration = duration
		self.next_time = None
		self.calculate_next_time()
		self.log('scheduled feed: %s' % self.next_time)

	def set_next(self):
		self.next_time = self.calculate_next_time()

	def calculate_next_time(self):
		now = datetime.datetime.now()
		feed_time = datetime.datetime(now.year, now.month, now.day, 
			self.hour, self.minute, self.second)
		if feed_time <= now:
			tomorrow = datetime.date.today() + datetime.timedelta(days=1)
			feed_time = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day, 
			self.hour, self.minute, self.second)

		self.next_time = feed_time

class CatFeederTwitter(Loggable):
	def __init__(self):
		twitter_api_key = os.environ.get('TWITTER_API_KEY')
		twitter_api_secret= os.environ.get('TWITTER_API_SECRET')
		twitter_access_token = os.environ.get('TWITTER_ACCESS_TOKEN')
		twitter_access_token_secret= os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')
		auth = tweepy.OAuthHandler(twitter_api_key, twitter_api_secret)
		auth.set_access_token(twitter_access_token, twitter_access_token_secret)
		self.tweepy = tweepy.API(auth)

	def post_feeding_success(self, scheduled_feed):
		filename = Camera.capture()
		self.tweepy.update_with_media(filename, status='[%s] Scarf was fed %s units.' % (datetime.datetime.now(), scheduled_feed.duration))

	def post_started(self, scheduled_feeds):
		schedule = ["%s:%s:%s" % (scheduled_feed.hour, scheduled_feed.minute, scheduled_feed.second) for scheduled_feed in scheduled_feeds]
		self.tweepy.update_status(status="[%s] Startup! Schedule=%s" % (datetime.datetime.now(), schedule))

class CatFeeder(Loggable):
	MOTOR_PIN = 22

	def __init__(self, scheduled_feeds):
		self.scheduled_feeds = scheduled_feeds
		self.current_feed = None
		self.ticker = TickerCounter()
		PinManager.setup_pin(self.MOTOR_PIN, GPIO.OUT)
		self.twitter = CatFeederTwitter()
		self.twitter.post_started(scheduled_feeds)

	def update(self):
		if not self.is_feeding:
			for scheduled_feed in self.scheduled_feeds:
				if scheduled_feed.next_time <= datetime.datetime.now():
					self.on_start_feeding(scheduled_feed)
					break

		if self.is_feeding:
			try:
				self.ticker.update()
			except TickerIncrementedEvent as e:
				if e.ticks_remaining == 0:
					self.on_stop_feeding()

	@property
	def is_feeding(self):
		return self.current_feed is not None

	def on_start_feeding(self, scheduled_feed):
		PinManager.write_pin(self.MOTOR_PIN, True)
		self.log("start feeding: %s" % scheduled_feed.next_time)
		self.current_feed = scheduled_feed
		self.ticker.count_from(scheduled_feed.duration)

	def on_stop_feeding(self):
		PinManager.write_pin(self.MOTOR_PIN, False)
		self.current_feed.calculate_next_time()
		self.log("stop feeding. next scheduled: %s" % self.current_feed.next_time)
		self.current_feed = None
		sleep(10)
		self.twitter.post_picture(self.current_feed)


now = datetime.datetime.now()

first_time = now + datetime.timedelta(seconds=2)
second_time = now + datetime.timedelta(seconds=60)

schedule = [
	FeedSchedule(15, 0, 0, 3), # 8 AM PST
	FeedSchedule(1, 0, 0, 3), # 6 PM PST
	FeedSchedule(17, 55, 0, 3) # 10:50 AM PST
]

PinManager.initalize()
cat_feeder = CatFeeder(schedule)

try:
	while True:
		cat_feeder.update() 
		time.sleep(SLEEP_INTERVAL)
except Exception as e:
	print e
finally:
	PinManager.write_pin(CatFeeder.MOTOR_PIN, False)
	PinManager.cleanup()



