import datetime


from hardware import PinManager, CatFeederMotor, TickerCounter, Camera, CatFeeder, DEBUG
from schedule import FeedSchedule
from social import CatFeederTwitter

tweet_at = 'tpsreporting'
sleep_interval = 0.1
motor_pin = 22
camera_flash_pin = 6
ticker_pin = 5
serving_size = 5

pin_manager = PinManager()
motor = CatFeederMotor(motor_pin, pin_manager)
ticker = TickerCounter(ticker_pin, pin_manager)
camera = Camera(camera_flash_pin, pin_manager, "/home/pi/webcam/")
twitter = CatFeederTwitter(camera, tweet_at)

if not DEBUG:
	scheduled_feeds = [
		FeedSchedule(15, 0, 0, serving_size), # 8 AM PST
		FeedSchedule(1, 0, 0, serving_size) # 6 PM PST
	]
else:
	now = datetime.datetime.now()
	first_time = now + datetime.timedelta(seconds=2)
	second_time = now + datetime.timedelta(seconds=60)
	scheduled_feeds = [
		FeedSchedule(first_time.hour, first_time.minute, first_time.second, serving_size), # 8 AM PST
		FeedSchedule(second_time.hour, second_time.minute, second_time.second, serving_size) # 6 PM PST
	]
	class DebugTickerCounter(TickerCounter):
		def __init__(self, ticker_pin, pin_manager):
			self.last_tick = None
			self.frequency = 1
			self.last_state =False
			super(DebugTickerCounter, self).__init__(ticker_pin, pin_manager)
			self.ticks_remaining = 0
			self.activated = False

		def read_state(self):
			now = datetime.datetime.now()
			if self.last_tick is None:
				self.last_tick = now

			if now > self.last_tick + datetime.timedelta(seconds=self.frequency):
				self.last_tick = now
				self.last_state = not self.last_state

			return self.last_state

	ticker = DebugTickerCounter(ticker_pin, pin_manager)

cat_feeder = CatFeeder(motor, ticker, twitter, scheduled_feeds, sleep_interval)
try:
	cat_feeder.start()
except KeyboardInterrupt as e:
	pass
finally:
	pin_manager.cleanup()
	motor.cleanup()
	camera.cleanup()
