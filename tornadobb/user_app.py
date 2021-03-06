#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#       user_app.py
#       
#       Copyright 2012 Di SONG <songdi19@gmail.com>
#       
#       This program is free software; you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation; either version 2 of the License, or
#       (at your option) any later version.
#       
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#       
#       You should have received a copy of the GNU General Public License
#       along with this program; if not, write to the Free Software
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#       MA 02110-1301, USA.

import tornado.web
from tornado.httpclient import *
from base import *
from mypostmarkup import render_bbcode
from settings import db_backend
from pytz import common_timezones
from util import *
import datetime, time
import hashlib
import os
import random

class MainHandler(BaseHandler):
	
	def get(self):
				
		if not self.current_user or self.current_user.get("is_auth",False):
			#guest
			guest_id = self.get_secure_cookie("_id")
			db_backend.do_set_guest_access_log(guest_id,time.time())
		
		elif self.get_secure_cookie("remember_me",False):
			#auto login
			expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=self.settings["tornadobb.session_expire"])
			self.set_secure_cookie("is_auth", 'True',expires=expires)
			db_backend.do_set_user_access_log(self.current_user["_id"],self.current_user["name"],time.time(),self.request.remote_ip)
			
		self.render('index.html',data=locals())
				
class PostNewTopicHandler(BaseHandler):
	
	@authenticated
	@url_parse
	@tornado.web.removeslash
	def get(self,category_id,forum_id, **kwargs):
		
		if not self.current_user.get("postable",True):
			self.redirect(self.settings["tornadobb.root_url"])
			return
		
		self.render('new_post.html',data=locals())
		
	@authenticated
	@url_parse
	@tornado.web.removeslash
	def post(self,category_id,forum_id, **kwargs):
		
		"""
		{'need_replay_for_attache': ['True'], '_xsrf': ['93e8153e619c4db2be146df3bd52c90d'], 'attache': ['http://adfadfad'], 'need_replay': ['True'], 'message': ['adfadfads'], 'subject': ['adfadf']}
		"""
		if not self.current_user.get("postable",True):
			self.redirect(self.settings["tornadobb.root_url"])
		
		user_id = self.current_user["_id"]
		user_name = self.current_user["name"]
		avatar = self.current_user.get("avatar",None)
		subject = self.get_argument("subject",None)
		content = self.get_argument("message",None)
		attach = []
		if "attach_url" in self.request.arguments and "attach_name" in self.request.arguments:
			urls = self.request.arguments["attach_url"]
			names = self.request.arguments["attach_name"]
			for i in xrange(0,len(urls)):
				attach.append({"name":names[i],"url":urls[i]})

		need_reply = bool(self.get_argument("need_reply1",False))
		need_reply_for_attach = bool(self.get_argument("need_reply2",False))
		
		now = time.time()
		topic = {
				"subject":subject,
				"create_time":now,
				"creater_id":user_id,
				"creater_name":user_name,
				"last_post_time":now,
				"last_poster_id":user_id,
				"last_poster_name":user_name,
				"sticky":False,
				"closed":False,
				"hidden":False,
				"dist":False,
				"dist_level":0,
				"need_reply" : need_reply,
				"need_reply_for_attach" : need_reply_for_attach,
			}
		
		post = {
				#"poster_id":user_id,
				#"poster_name":user_name,
				#"poster_role":"Member",
				#"poster_avatar":".jpg",
				#"poster_signature":"[b]I am a good man.[/b]",
				#"poster_register_time":time.time(),
				#"poster_posts_num":100,
				#"poster_online":True,
				"post_time":now,
				"content":content,
				}
		
		if attach:
			post["attach"] = attach
		
		topic["posts"] = [post]
		topic_id = db_backend.do_create_new_topic(category_id,forum_id,topic)
		if topic_id:
			self.redirect('/'.join([self.settings["tornadobb.root_url"],'topic',category_id,forum_id,topic_id]) + '/')
		else:
			self.write_erro(500)
		return
		

class ReplyTopicHandler(BaseHandler):
	
	@authenticated
	@url_parse
	def post(self,category_id,forum_id,topic_id, **kwargs):

		post = {
				"poster_id":self.current_user["_id"],
				"post_time":time.time(),
				"content":self.get_argument("message"),
			}
		if db_backend.do_reply_topic(category_id,forum_id,topic_id,self.current_user["name"],post):
			self.redirect('/'.join([self.settings["tornadobb.root_url"],'topic',category_id,forum_id,topic_id]) + '/')
		else:
			self.write_error(500)
		
class PostEditHandler(BaseHandler):
	
	@authenticated
	@url_parse
	@load_permission
	def post(self,category_id,forum_id,topic_id,**kwargs):
		
		
		post_id = self.get_argument("post_id")
		poster_id = self.get_argument("poster_id")
		message = self.get_argument("message")
		current_id = self.current_user["_id"]
		if poster_id == current_id or "edit_post" in kwargs.get("permission"):
			post = {
				"_id" : post_id,
				"editer_id":current_id,
				"editer_name":self.current_user["name"],
				"edit_time":time.time(),
				"content":message,
				}
			if db_backend.do_edit_post(forum_id,topic_id,post):
				self.redirect('/'.join([self.settings["tornadobb.root_url"],'topic',category_id,forum_id,topic_id]) + "/")
			else:
				self.write_error(500)
				return
		else:
			self.write_error(403)
			return
	
class PostDeleteHandler(BaseHandler):
	
	@authenticated
	@url_parse
	@load_permission
	def get(self,category_id,forum_id,topic_id,**kwargs):

		#print self.request.arguments
		permission = kwargs.get("permission",[])
		post_id = self.get_argument("post_id")
		if "delete_post" in permission:
			post = {
				"_id" : post_id,
				"editer_id":self.current_user["_id"],
				"editer_name":self.current_user["name"],
				"edit_time":time.time(),
				}
			if db_backend.do_delete_post(forum_id,topic_id,post):
				self.redirect('/'.join([self.settings["tornadobb.root_url"],'topic',category_id,forum_id,topic_id]) + "/")
			else:
				self.write_error(500)
				return
		else:
			self.write_error(403)
			return
		
class QuoteHandler(BaseHandler):
	
	@authenticated
	@url_parse
	def post(self,category_id,forum_id,topic_id, **kwargs):
		#print self.request.arguments
		
		post = {
				"poster_id":self.current_user["_id"],
				"post_time":time.time(),
				"content":self.get_argument("message"),
			}
		if db_backend.do_reply_topic(category_id,forum_id,topic_id,self.current_user["name"],post):
			self.redirect('/'.join([self.settings["tornadobb.root_url"],'topic',category_id,forum_id,topic_id]) + "/")
		else:
			self.write_error(500)

class TopicManagementHandler(BaseHandler):
	
	@authenticated
	@url_parse
	@load_permission
	def get(self,category_id,forum_id,topic_id,**kwargs):

		permission = kwargs.get("permission",[])
		command = self.get_argument("c",None)# jump to page
		#print command
		errors = None
		if command and command in permission:
			if command == "sticky" and not db_backend.do_make_topic_sticky(forum_id,topic_id):
				errors = ["Fail to make it sticky"]
			elif command == "distillate" and not db_backend.do_make_topic_dist(forum_id,topic_id):
				errors = ["Fail to make it distillate"]
			elif command == "close_topic" and not db_backend.do_make_topic_close(forum_id,topic_id):
				errors = ["Fail to make it close"]
			elif command == "hide_topic" and not db_backend.do_make_topic_hidden(forum_id,topic_id):
				errors = ["Fail to make it hidden"]
			elif command == "unhide_topic" and not db_backend.do_make_topic_unhidden(forum_id,topic_id):
				errors = ["Fail to make it unhidden"]
			elif  command == "delete_topic" and not db_backend.do_make_topic_delete(category_id,forum_id,topic_id):
				errors = ["Fail to make it delete"]
			elif command == "move_topic":
				param = self.get_argument("p",None)# new category_id/new forum_id
				if param:
					new_category_id_and_new_forum_id = param.split("/")
					new_category_id = new_category_id_and_new_forum_id[0]
					new_forum_id = new_category_id_and_new_forum_id[1]
					if not db_backend.do_make_topic_move(category_id,forum_id,new_category_id,new_forum_id,topic_id):
						errors = ["Fail to make it move"]  
				else:
					self.write_error(404)
					return
				
			elif command == "highlight":
				param = self.get_argument("p",None)# new category_id/new forum_id
				if not param or param not in self.settings["tornadobb.highlight_settings"]:
					self.write_error(404)
					return
				if not db_backend.do_make_topic_highlight(forum_id,topic_id,param):
					errors = ["Fail to make it highlight"]
			
			if errors:
				self.write_error(500)
				return
			else:
				self.redirect( "/".join([self.settings["tornadobb.root_url"],"forum",category_id,forum_id]) + "/")
		else:
			self.write_error(403)
			return

class SearchHandler(BaseHandler):
	
	@tornado.web.removeslash
	def get(self):
		return self.render("search.html",data={})
	
	def post(self):
		
		search_field = self.get_argument("search_field",None)
		if search_field:
			category_forum_id = self.get_argument("id",None)
			category_id_and_forum_id = category_forum_id.split("/")
			category_id = category_id_and_forum_id[0]
			forum_id = category_id_and_forum_id[1]
			topics = db_backend.do_search_topic_name(forum_id,search_field)
			return self.render("search.html",data=locals())
		else:
			self.redirect(self.reverse_url("search_page"))
	
class MarkitupPreviewHandler(BaseHandler):
	
	@authenticated
	def check_xsrf_cookie(self):
		pass
		
	@authenticated
	def post(self):

		self.write(render_bbcode(self.get_argument("data"),"UTF-8"))
	
class UserLoginHandler(BaseHandler):
	
	@tornado.web.removeslash
	def get(self):

		next = self.get_argument("next",self.reverse_url("home_page"))
		return self.render("login.html",data={"next":next})
		
	def post(self):
	
		username = self.get_argument('username',None)
		password =  self.get_argument('password',None)
		remeber_me = self.get_argument('save_pass',False)
		next = self.get_argument('next',self.reverse_url("home_page"))

		if not username or not password:
			self.write_error(403)
		m = hashlib.md5()
		m.update(password)
		password = m.hexdigest().upper()

		response,user = db_backend.do_user_login(username,password,time.time(),self.xsrf_token)
		if response == "ok":
			
			self.clear_all_cookies()
			self.set_cookie("_xsrf",self.xsrf_token)			
			tornadobb_settings = self.settings
			self.set_secure_cookie("_id",str(user["_id"]))
			self.set_secure_cookie("name",user["name"])
			locale = user.get("locale",tornadobb_settings["tornadobb.default_locale"])
			if locale:
				self.set_secure_cookie("locale",locale)
			postable = user.get("postable",True)
			if not postable:
				self.set_secure_cookie("postable","False")
			closed = user.get("closed",False)
			if closed:
				self.set_secure_cookie("closed","True")
			avatar = user.get("avatar",None)
			if avatar:
				 self.set_secure_cookie("avatar",avatar)

			role = user.get("role",None)
			if role:
				self.set_secure_cookie("role",role)
				
			tz = user.get("tz",None)
			if tz:
				self.set_secure_cookie("tz",tz)
				tz_obj = timezone(tz)
			else:
				tz_obj = self.settings["tornadobb.timezone_obj"]
				
			style = user.get("style",None)
			if style:
				self.set_secure_cookie("style",style)
					
			if remeber_me:
				self.set_secure_cookie("save_pass",remeber_me)
				
			expires = datetime.datetime.now(tz_obj) + datetime.timedelta(seconds=self.settings["tornadobb.session_expire"])
			self.set_secure_cookie("is_auth", '1',expires=expires)
			
			self.redirect(next)
			return
			
		elif response == "fail":
			errors = ["Wrong user name or password"]
			
		elif response == "not_verify":
			errors = ["Your account is not actived yet","please active it with the active email we sent to you before"]
			
		elif response == "closed":
			 errors = ["Your account is closed"]
			
		self.render("login.html",data=locals())
		return 
			
class UserLogoutHandler(BaseHandler):
	
	@tornado.web.removeslash
	def get(self):
		
		if not self.get_secure_cookie("save_pass",False):
			locale = self.get_secure_cookie("locale")
			self.clear_all_cookies()
			if locale:
				self.set_secure_cookie("locale",locale)
		else:
			self.clear_cookie("is_auth")
		user_id = self.get_secure_cookie("_id")
		if user_id:
			db_backend.do_user_logout(user_id)
		self.redirect(self.reverse_url("home_page"))

class UserRegisterHandler(BaseHandler):
	
	@tornado.web.removeslash
	def get(self):
		
		return self.render("register.html",data={})
		
	def post(self):
		#print self.request.arguments	
		username = self.get_argument('username')
		email = self.get_argument('email1')
		#check username and email
		if db_backend.do_check_user_name(username):
			errors = ["This username: %s has already been used" % username]
		elif db_backend.do_check_user_email(email):
			errors = ["This email: %s has already been used" % email]
		else:
			
			display_email = bool(self.get_argument('display_email',False))
			password = self.get_argument('password1')
			m = hashlib.md5()
			m.update(password)
			password = m.hexdigest().upper()
			
			user = {
					"name" : username,
					"password": password,
					"email" : email,
					"registered_time":time.time(),
					"display_email":display_email,
					}
					
			if db_backend.do_user_register(user):
				send_verify_email(self,email,username,password)
				messages = ["A active email has already been sent to " + email,"Please active your account before login"]
			else:
				self.write_error(500)
				return
		
		self.render("register.html",data=locals())
		return

class UserProfileHandler(BaseHandler):
	
	@authenticated
	@tornado.web.removeslash
	def get(self):
		
		user = db_backend.do_show_user_info_with_id(self.current_user["_id"])
		if user:
			self.render("user_essentials.html",data=locals())
		else:
			self.write_error(404)
			return
			
	@authenticated
	def post(self):
		
		tz = self.get_argument("tz",None)
		if tz and db_backend.do_update_user_timezone(self.current_user["_id"],tz):
			self.set_secure_cookie("tz",tz)
			self.redirect(self.reverse_url("profile_page"))
		else:
			self.write_error(500)
			return

class UserAvatarHandler(BaseHandler):
	@authenticated
	@tornado.web.removeslash
	def get(self):
		
		self.render("user_avatar.html",data=locals())
	
	def post(self):
				
		user_id = self.get_argument("_id",None)
		xsrf_value = self.get_argument("xsrf",None)
		if not user_id or not xsrf_value or not db_backend.do_check_xsrf_for_avatar_upload(user_id,xsrf_value):
			self.write("403")
			return
			
		name,ext = os.path.splitext(self.get_argument("Filename"))
		file1 = self.request.files['Filedata'][0]
		avatar_file = open(self.settings["tornadobb.root_path"] + "/static/avatar/" + user_id + ext, 'w')
		avatar_file.write(file1['body'])
		avatar_file.close()
		
		user = db_backend.do_show_current_avatar_name(user_id)
		if user:
			current_avatar_ext = user.get("avatar",None)
			if current_avatar_ext:
				if current_avatar_ext == ext:
					self.write("OK")
				else:
					os.remove(self.settings["tornadobb.root_path"] + "/static/avatar/" + user_id + current_avatar_ext)
				
			db_backend.do_change_avatar_name(user_id,ext)
			self.write("RELOGIN")
			
		else:	
			self.write("FAIL")
		
		self.flush()
		return

class UserSignatureHandler(BaseHandler):
	@authenticated
	@tornado.web.removeslash
	def get(self):

		signature = db_backend.do_show_user_signature(self.current_user["_id"])
		if not signature:
			signature = ""
		self.render("user_personality.html",data=locals())
		
	@authenticated
	def post(self):
		#print self.request.arguments
		signature = self.get_argument("signature","")
		if db_backend.do_save_user_signature(self.current_user["_id"],signature):
			self.redirect(self.request.path)
		else:
			errors = ["Fail to save signature"]
			self.render("user_personality.html",data=locals())

class UserPasswordHandler(BaseHandler):
	@authenticated
	@tornado.web.removeslash
	def get(self):
		
		self.render("user_password.html",data=locals())
		
	@authenticated
	def post(self):
		#print self.request.arguments
		
		old_password = self.get_argument("old_password",None)
		new_password = self.get_argument("new_password1",None)
		
		if old_password and new_password:
			m = hashlib.md5()
			m.update(old_password)
			old_password = m.hexdigest().upper()
			m.update(new_password)
			new_password = m.hexdigest().upper()
			if db_backend.do_update_user_password(self.current_user["_id"],old_password,new_password):
				self.redirect(self.reverse_url("profile_page"))
			else:
				errors = ["Fail to change password"]
				self.render("user_password.html",data=locals())

class UserEmailHandler(BaseHandler):
	
	@authenticated
	@tornado.web.removeslash
	def get(self):

		self.render("user_email.html",data=locals())
		
	@authenticated
	def post(self):
		#print self.request.arguments
		
		password = self.get_argument("password",None)
		new_email = self.get_argument("new_email1",None)
		
		if password and new_email:
			m = hashlib.md5()
			m.update(password)
			password = m.hexdigest().upper()
			if db_backend.do_update_user_email(self.current_user["_id"],password,new_email):
				send_verify_email(self,new_email,self.current_user["name"],password)
				messages = ["A new active email has already been sent to you new email address","Please reactive your account when next login"]
				self.render("user_email.html",data=locals())
			else:
				errors = ["Fail to verify your password"]
				self.render("user_email.html",data=locals())

class UserDisplayHandler(BaseHandler):
	
	@authenticated
	@tornado.web.removeslash
	def get(self):
		
		self.render("user_display.html",data=locals())
		
	@authenticated
	def post(self):
		#print self.request
		style = self.get_argument("style",None)
		if style:
			if db_backend.do_update_user_display(self.current_user["_id"],style):
				self.set_secure_cookie("style",style)
				self.redirect(self.request.path)
			else:
				self.write_error(500)
				return
		else:
			self.write_error(404)
			return

class UserPrivacyHandler(BaseHandler):
	@authenticated
	@tornado.web.removeslash
	def get(self):
		
		display_email = db_backend.do_show_display_email_option(self.current_user["_id"])
		self.render("user_privacy.html",data=locals())
		
	@authenticated
	def post(self):
		display_email = self.get_argument("display_email",None)
		if display_email:
			if not db_backend.do_update_user_privacy(self.current_user["_id"],True):
				self.write_error(500)
				return
		elif not db_backend.do_update_user_privacy(self.current_user["_id"],False):
			self.write_error(500)
			return
		
		self.redirect(self.request.path)
		return

class ResendVerifyMailHandler(BaseHandler):
		
	@tornado.web.removeslash	
	def get(self):
		
		self.render("resend_active_email.html",data=locals())
		
	def post(self):
		
		#print self.request
		
		username = self.get_argument("username")
		password = self.get_argument("password")
		if username and password:
			m = hashlib.md5()
			m.update(password)
			password = m.hexdigest().upper()
			email = db_backend.do_show_user_email_with_username_password(username,password)
			if email:
				send_verify_email(self,email,username,password)
				messages = ["An active account email has alerady sent to " + email]

			else:
				errors = ["Wrong username or email address"]
			self.render("resend_active_email.html",data=locals())
		else:
			self.write_error(404)
			return

class UserActiveHandler(BaseHandler):
	
	def get(self):
		#print self.request.arguments
		username = self.get_argument("u",None)
		password = self.get_argument("p",None)
		if username and password and db_backend.do_active_user_account(username,password):
			messages = ["Your account is actived now,please login"]
			next = self.reverse_url("home_page")
			self.render("login.html",data=locals())
		else:
			self.write_error(500)
			return

class TimezoneHandler(BaseHandler):
	
	@authenticated
	def get(self):
		area = self.get_argument("area",None)
		if area:
			tz = filter(lambda x: x.startswith(area),common_timezones)
			self.write({"tz":tz})
			return

class UserForgetPasswordHandler(BaseHandler):

	@tornado.web.removeslash
	def get(self):
		
		self.render("forget_password.html",data=locals())
	
	def post(self):
		username = self.get_argument("username",None)
		email = self.get_argument("email",None)
		if username and email:
			user_id = db_backend.do_show_user_id_with_username_email(username,email)
			new_password = "".join(random.sample(['a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z','A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'], 5))
			m = hashlib.md5()
			m.update(new_password)
			hash_new_password = m.hexdigest().upper()
			if user_id and db_backend.do_reset_user_password(user_id,hash_new_password):
				send_forget_password_email(self,email,username,new_password)
				messages = ["Your new password has already been sent to " + email]	
			else:
				errors = ["Wrong username or email"]
				
			self.render("forget_password.html",data=locals())
			
		else:
			self.write_error(404)
			return
			
class UserInfoHandler(BaseHandler):
	
	@authenticated
	def get(self):
		user_id = self.get_argument("uid",None)
		if user_id:
			user = db_backend.do_show_user_info_with_id(user_id)
			if user:
				self.render("user_info.html",data = locals())
				return
				
		self.write_error(404)
		return
		
class ForumRulesHandler(BaseHandler):
	
	@tornado.web.removeslash
	def get(self):
		
		self.render("rules.html",data={})
		
class ChangeLanguageHandler(BaseHandler):
	
	@tornado.web.removeslash
	def get(self):
		
		language = self.get_argument("l",None)
		if language:
			self.set_secure_cookie("locale",language)
		
		self.redirect(self.reverse_url("home_page"))

def send_forget_password_email(request_handler,email_address,username,password):
	
	subject = tornado.escape.to_unicode("New password from" + request_handler.settings["tornadobb.forum_title"])
	message = tornado.escape.to_unicode(request_handler.render_string("forget_password_email.html",username=username,password=password))
	body='_xsrf='+ request_handler.xsrf_token+'&receiver='+ email_address +'&subject='+ subject +'&plain='+ message + "&html=" + message
	http_client = AsyncHTTPClient()
	request = request_handler.request
	http_client.fetch(request.protocol + "://" + request.host + request_handler.settings["tornadobb.root_url"] + "/sendmail", None ,method ="POST", body=body , headers = request.headers)


def send_verify_email(request_handler,email_address,username,password):
	subject = tornado.escape.to_unicode("Active account email from " + request_handler.settings["tornadobb.forum_title"])
	message = tornado.escape.url_escape(tornado.escape.to_unicode(request_handler.render_string("active_email.html",username=username,password=password)))
	body='_xsrf='+ request_handler.xsrf_token+'&receiver='+ email_address +'&subject=' + subject +'&plain='+ message + "&html=" + message
	http_client = AsyncHTTPClient()
	request = request_handler.request
	http_client.fetch(request.protocol + "://" + request.host + request_handler.settings["tornadobb.root_url"] + "/sendmail", None ,method ="POST", body=body , headers = request.headers)


class ForumHandler(BaseHandler):
	@url_parse
	@load_permission
	def get(self,category_id,forum_id,page_param,**kwargs):
				
		filter_view = self.get_argument("f","all")#filter
		if filter_view == "hide" and "hide_topic" not in kwargs.get("permission"):
			self.write_error(403)
			return

		current_page_no = page_param["current_page"] #current page
		jump_to_page_no = page_param["jump_to_page"]# jump to page	
		pages_num = page_param["total_pages_num"] #total page count
		total_items_num = page_param["total_topics_num"] #total items
		
		order_by = self.get_argument("o","post")#order
		dist_level = self.settings["tornadobb.distillat_threshold"]
		topics_num_per_page = self.settings["tornadobb.topics_num_per_page"]
		
		if pages_num == jump_to_page_no:
			# go to the lastest page
			topics = db_backend.do_jump_to_lastest_page(forum_id,topics_num_per_page,filter_view,order_by,dist_level)
			jump_to_page_no = int(pages_num)
		
		elif jump_to_page_no > 1:
			#jump to some page
			current_page_top = page_param["top_topic_time"]#top item
			current_page_bottom = page_param["bottom_topic_time"] #bottom item
					
			offset = jump_to_page_no - current_page_no
			if offset == 1:
				#just go to next one page
				topics = db_backend.do_show_next_page_topics(forum_id,current_page_bottom,topics_num_per_page,filter_view,order_by,dist_level)
			elif offset > 1:
				topics = db_backend.do_jump_back_to_show_topics(forum_id,current_page_bottom,topics_num_per_page,current_page_no,jump_to_page_no,filter_view,order_by,dist_level)
			elif offset == -1:
				topics = db_backend.do_show_prev_page_topics(forum_id,current_page_top,topics_num_per_page,filter_view,order_by,dist_level)
			elif offset < -1:
				topics = db_backend.do_jump_forward_to_show_topics(forum_id,current_page_top,topics_num_per_page,current_page_no,jump_to_page_no,filter_view,order_by,dist_level)
			else:
				topics = db_backend.do_jump_to_first_page(forum_id,topics_num_per_page,filter_view,order_by,dist_level)
		
		else:
			
			from_page = self.get_argument("fp",1)
			if from_page > 1:
				pass
			else:	
				# go to the first page
				topics = db_backend.do_jump_to_first_page(forum_id,topics_num_per_page,filter_view,order_by,dist_level)
		
		if topics:
			current_page_top = topics[0]["last_post_time"]
			current_page_bottom = topics[-1]["last_post_time"]
			pagination_obj = db_backend.do_create_topic_pagination(forum_id,jump_to_page_no,current_page_top,current_page_bottom,topics_num_per_page,pages_num,total_items_num,filter_view,order_by,dist_level)
		else:
			pagination_obj = db_backend.do_create_topic_pagination(forum_id,jump_to_page_no,0.0,0.0,topics_num_per_page,pages_num,total_items_num,filter_view,order_by,dist_level)
		
		if not pagination_obj:
			self.write_error(500)
			return
		
		pagination_obj["category_id"] = category_id
		pagination_obj["forum_id"] = forum_id
		
		forum_path = self.request.path
		
		self.render('forum.html',data=locals())

class TopicHandler(BaseHandler):

	@url_parse
	@load_permission
	def get(self,category_id,forum_id,topic_id,page_param,**kwargs):
		
		permission = kwargs.get("permission")
		filter_view = self.get_argument("f","all")
		
		jump_to_page_no = page_param["jump_to_page"]# jump to page	
		pages_num = page_param["total_pages_num"] #total page count
		total_items_num = page_param["total_topics_num"] #total items
				
		posts_num_per_page = self.settings["tornadobb.posts_num_per_page"]
		expire_time = time.time() - self.settings["tornadobb.session_expire"]
		topic_obj  = db_backend.do_show_topic_posts(forum_id,topic_id,jump_to_page_no,posts_num_per_page,expire_time,filter_view)

		if not topic_obj:
			self.write_error(500)
			return
		
		if jump_to_page_no == 1:
			db_backend.do_add_topic_views_num(forum_id,topic_id)	
		##print topic_obj
		pagination_obj = db_backend.do_create_post_pagination(forum_id,topic_id,jump_to_page_no,posts_num_per_page,pages_num,total_items_num,filter_view)
		if not pagination_obj:
			self.write_error(500)
			return
		pagination_obj["category_id"] = category_id
		pagination_obj["forum_id"] = forum_id
		pagination_obj["topic_id"] = topic_id
		#for modules.pagenation_post
		pagination_obj["from_query"] = self.request.query	
		# get current user whether alreay reply this topic boolean
		hide_content = topic_obj.get("need_reply",False)

		hide_attach = topic_obj.get("need_reply_for_attach",False)
		#current_user = self.current_user
		if hide_content or hide_attach:
			#TODO: HOW can current user get replies
			if self.current_user and "_id" in self.current_user and db_backend.do_check_already_reply(forum_id,topic_id,self.current_user["_id"]):
				hide_content = False
				hide_attach = False
		
		#for modules.Forum_Crumbs		
		from_query = self.request.query
		
		self.render('topic.html',data=locals())

class UserTopicsHandler(BaseHandler):
	
	@authenticated
	def get(self):
		url_parameters = self.request.path.partition(self.settings["tornadobb.root_url"])[2].split("/")
		user_id = url_parameters[3]
		self.render("user_topics.html",data=locals())

		
class UserRepliesHandler(BaseHandler):
	
	@authenticated
	def get(self):
		url_parameters = self.request.path.partition(self.settings["tornadobb.root_url"])[2].split("/")
		user_id = url_parameters[3]
		self.render("user_replies.html",data=locals())
		


class UserTopicsRepliesHandler(BaseHandler):
	
	@authenticated
	@url_parse
	def get(self,category_id,forum_id,user_id,target,page_param,**kwargs):
		
		jump_to_page_no = page_param["jump_to_page"]
		pages_num = page_param["total_pages_num"]
		total_items_num = page_param["total_items_num"]
		topics_num_per_page = self.settings["tornadobb.topics_num_per_page"]
		
		if target == "topics":
			topics = db_backend.do_show_user_topics(user_id,forum_id,jump_to_page_no,topics_num_per_page)
			pagination_obj = db_backend.do_create_user_topics_pagination(user_id,category_id,forum_id,jump_to_page_no,topics_num_per_page,pages_num,total_items_num)
		
		elif target == "replies":
			topics = db_backend.do_show_user_replies(user_id,forum_id,jump_to_page_no,topics_num_per_page)
			pagination_obj = db_backend.do_create_user_replies_pagination(user_id,category_id,forum_id,jump_to_page_no,topics_num_per_page,pages_num,total_items_num)
		
		pagination_obj["category_id"] = category_id
		pagination_obj["forum_id"] = forum_id
		pagination_obj["target"] = target
			
		self.render("user_topics.html",data=locals())
		

class UserReplies2Handler(BaseHandler):
	
	@authenticated
	@url_parse
	def get(self,category_id,forum_id,user_id,target, page_param,**kwargs):
		
		jump_to_page_no = page_param["jump_to_page"]
		pages_num = page_param["total_pages_num"]
		total_items_num = page_param["total_items_num"]
		topics_num_per_page = self.settings["tornadobb.topics_num_per_page"]
		
		topics = db_backend.do_show_user_replies(user_id,forum_id,jump_to_page_no,topics_num_per_page)
			
		pagination_obj = db_backend.do_create_user_replies_pagination(user_id,category_id,forum_id,jump_to_page_no,topics_num_per_page,pages_num,total_items_num)
		pagination_obj["category_id"] = category_id
		pagination_obj["forum_id"] = forum_id
		pagination_obj["target"] = "replies"
			
		self.render("user_replies.html",data=locals())
