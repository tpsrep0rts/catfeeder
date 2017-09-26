import os
from loggable import Loggable

class CatFeederTwitter(Loggable):
	def __init__(self, camera, tweet_at):
		import tweepy
		self.camera = camera
		self.tweet_at = tweet_at

		twitter_api_key = os.environ.get('TWITTER_API_KEY')
		twitter_api_secret= os.environ.get('TWITTER_API_SECRET')
		twitter_access_token = os.environ.get('TWITTER_ACCESS_TOKEN')
		twitter_access_token_secret= os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')
		auth = tweepy.OAuthHandler(twitter_api_key, twitter_api_secret)
		auth.set_access_token(twitter_access_token, twitter_access_token_secret)
		self.tweepy = tweepy.API(auth)

	def update_status(self, message, take_picture=False):
		from hardware import CameraFailedException
		return
		if take_picture:
			try:
				filename = self.camera.capture()
			except CameraFailedException as e:
				filename = None

			if not filename:
				self.log_error("Failed to caputure picture")
				return self.update_status(message, False)

			self.tweepy.update_with_media(filename, status=self.format_message(message))
		else:
			self.tweepy.update_status(status=self.format_message(message))

	def format_message(self, message):
		message = "%s @%s" % (message, self.tweet_at)
		return message
