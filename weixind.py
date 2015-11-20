#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:     weixind.py
# Author:       Liang Cha<my_token@gmail.com>
# CreateDate:   2014-05-15

import os
import web
import time
import types
import urllib
import urllib2
import hashlib
import memcache
import RPi.GPIO as GPIO
from RPIO import PWM
from lxml import etree
from weixin import WeiXinClient
from weixin import APIError
from yeelink import current_time
from yeelink import YeeLinkClient


_TOKEN = 'my_token'
_URLS = (
    '/weixin', 'weixinserver',
)


def _check_hash(data):
    signature = data.signature
    timestamp = data.timestamp
    nonce = data.nonce
    list = [_TOKEN, timestamp, nonce]
    list.sort()
    sha1 = hashlib.sha1()
    map(sha1.update, list)
    hashcode = sha1.hexdigest()
    if hashcode == signature:
        return True
    return False


def _check_user(user_id):
    user_list = ['obMnLt3bf7t65jyEsa7vOtXphdu4']
    if user_id in user_list:
        return True
    return False

def _get_user_info(wc):
    info_list = []
    wkey = 'wacthers_%s' % wc.app_id
    mc = memcache.Client(['192.168.1.12:11211'], debug=0)
    id_list = mc.get(wkey)
    if id_list is None:
        return info_list
    for open_id in id_list:
        req = wc.user.info._get(openid=open_id, lang='zh_CN')
        name ='%s' %(req.nickname)
        place = '%s,%s,%s' %(req.country, req.province, req.city)
        sex = '%s' %(u'男') if (req.sex == 1) else u'女'
        info_list.append({'name':name, 'place':place, 'sex':sex})
    return info_list


def _arduino_client(data):
    import select
    import socket
    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.setblocking(False)
    inputs = [c]
    c.connect(('192.168.1.10', 6666))
    c.sendall(data)
    readable, writeable, exceptional = select.select(inputs, [], [], 3)
    if not readable:
        return '{"errno": -1, "msg":"wait response timeout"}'
    else:
        return c.recv(1024)


def _take_snapshot(addr, port, client):
    import ipcam
    cam = ipcam.IPCamClient('10.0.0.101', 34567, 'ckmx', '159357852')
    vd = cam.photoaf.get()
    return client.media.upload.file(type='image', pic=vd)


#def _take_snapshot(addr, port, client):
#    url = 'http://%s:%d/?action=snapshot' %(addr, port)
#    req = urllib2.Request(url)
#    resp = urllib2.urlopen(req, timeout = 2)
#    return client.media.upload.file(type='image', pic=resp)


def _do_event_subscribe(server, fromUser, toUser, doc):
    return server._reply_text(fromUser, toUser, u'hello!')


def _do_event_unsubscribe(server, fromUser, toUser, doc):
    return server._reply_text(fromUser, toUser, u'bye!')


def _do_event_SCAN(server, fromUser, toUser, doc):
    pass


def _do_event_LOCATION(server, fromUser, toUser, doc):
    pass


def _do_event_CLICK(server, fromUser, toUser, doc):
    key = doc.find('EventKey').text
    try:
        return _weixin_click_table[key](server, fromUser, toUser, doc)
    except KeyError, e:
        print '_do_event_CLICK: %s' %e
        return server._reply_text(fromUser, toUser, u'Unknow click: '+key)


_weixin_event_table = {
    'subscribe'     :   _do_event_subscribe,
    'unsbscribe'    :   _do_event_unsubscribe,
    'SCAN'          :   _do_event_SCAN,
    'LOCATION'      :   _do_event_LOCATION,
    'CLICK'         :   _do_event_CLICK,
}


def _do_click_V1001_USER_LIST(server, fromUser, toUser, doc):
    reply_msg = ''
    user_list = None
    try:
        user_list = _get_user_info(server.client)
    except Exception, e:
        reply_msg = '_get_user_info error: %r', e
        server.client.refurbish_access_token()
    if user_list:
        index = 0
        for user in user_list:
            reply_msg = '%s[%d]%s|%s|%s\n' %(reply_msg, index, user['name'], user['place'], user['sex'])
            index += 1
    else:
        if not reply_msg:
            reply_msg = 'None user.'
    return server._reply_text(fromUser, toUser, reply_msg)


def _do_click_V1001_GOOD(server, fromUser, toUser, doc):
    msg = '你已经加入监控队列。'
    wkey = 'wacthers_%s' % server.client.app_id
    try:
        mc = memcache.Client(['192.168.1.12:11211'], debug=0)
        wlist = mc.get(wkey)
        if wlist is None:
            mc.set(wkey, [])
            wlist = [fromUser]
        elif fromUser in wlist:
            del wlist[wlist.index(fromUser)]
            msg = '你已经退出监控队列。'
        else:
            wlist.append(fromUser)
        mc.replace(wkey, wlist)
    except Exception, e:
        msg = '_do_click_V1001_GOOD error, %r' % e
    return server._reply_text(fromUser, toUser, msg)


#def _do_click_V1001_LED_ON(server, fromUser, toUser, doc):
#    data = '{"name":"digitalWrite","para":{"pin":7,"value":1}}'
#    buf = _arduino_client(data)
#    data = eval(buf)
#    errno = None
#    reply_msg = None
#    if type(data) is types.StringType:
#        return server._reply_text(fromUser, toUser, data)
#    errno = data['errno']
#    if errno == 0:
#        reply_msg = '成功点亮'
#    else:
#        reply_msg = buf
#    return server._reply_text(fromUser, toUser, reply_msg)


def _do_click_V1001_LED_ON(server, fromUser, toUser, doc):
    GPIO.output(18, GPIO.HIGH)
    if GPIO.input(18):
        reply_msg = '成功点亮'
    else:
        reply_msg = '没有点亮'
    return server._reply_text(fromUser, toUser, reply_msg)



#def _do_click_V1001_LED_OFF(server, fromUser, toUser, doc):
#    data = '{"name":"digitalWrite", "para":{"pin":7, "value":0}}'
#    buf = _arduino_client(data)
#    data = eval(buf)
#    errno = None
#    reply_msg = None
#    if type(data) is types.StringType:
#        return server._reply_text(fromUser, toUser, data)
#    errno = data['errno']
#    if errno == 0:
#        reply_msg = '成功关闭'
#    else:
#        reply_msg = buf
#    return server._reply_text(fromUser, toUser, reply_msg)


def _do_click_V1001_LED_OFF(server, fromUser, toUser, doc):
    GPIO.output(18, GPIO.LOW)
    if not GPIO.input(18):
        reply_msg = '成功熄灭'
    else:
        reply_msg = '没有熄灭'
    return server._reply_text(fromUser, toUser, reply_msg)



#def _do_click_V1001_C_RIGHT(server, fromUser, toUser, doc):
    #data = '{"name":"servo","para":{"value":1}}'
    #buf = _arduino_client(data)
    #data = eval(buf)
    #errno = None
    #reply_msg = None
    #if type(data) is types.StringType:
        #return server._reply_text(fromUser, toUser, data)
    #errno = data['errno']
    #if errno == 0:
        #reply_msg = "当前角度: %d" %(data['resp']['v'])
    #else:
        #reply_msg = buf
    #return server._reply_text(fromUser, toUser, reply_msg)


#def _do_click_V1001_C_LEFT(server, fromUser, toUser, doc):
    #data = '{"name":"servo","para":{"value":-1}}'
    #buf = _arduino_client(data)
    #data = eval(buf)
    #errno = None
    #reply_msg = None
    #if type(data) is types.StringType:
        #return server._reply_text(fromUser, toUser, data)
    #errno = data['errno']
    #if errno == 0:
        #reply_msg = "当前角度: %d" %(data['resp']['v'])
    #else:
        #reply_msg = buf
    #return server._reply_text(fromUser, toUser, reply_msg)


(USW_PLS, USW_SUB, USW_OBS) = range(3)


def _update_servo_width(operation, value=45):
    """TODO: Docstring for _update_servo_width.

    :operation: USW_PLS|USW_SUB|USW_OBS
    :value: USW_OBS will be use.
    :returns: current width; return 0 if operation error.

    """
    wkey = 'wx_servo'
    #servo = PWM.Servo()
    mc = memcache.Client(['192.168.1.12:11211'], debug=0)
    width = mc.get(wkey)
    if width is None:
        mc.set(wkey, 45)
        width = 45

    if operation == USW_PLS:
        width += 30
    elif operation == USW_SUB:
        width -= 30
    elif operation == USW_OBS:
        width = value
    else:
        return 0

    if width > 205:
        width = 205
    elif width < 45:
        width = 45

    mc.replace(wkey, width)
    #servo.set_servo(17, width * 10)
    #time.sleep(1)
    #servo.stop_servo(17)
    if PWM.is_setup() == 0:
        PWM.setup()
    if PWM.is_channel_initialized(0) == 0:
        PWM.init_channel(0)
    PWM.add_channel_pulse(0, 17, 0, width)
    time.sleep(1)
    #PWM.clear_channel_gpio(0, 17)
    PWM.clear_channel(0)
    #PWM.cleanup()
    return width


def _do_click_V1001_C_RIGHT(server, fromUser, toUser, doc):
    try:
        width = _update_servo_width(USW_PLS)
        msg = 'servo width is %d.' % width
    except Exception, e:
        msg = '_do_click_V1001_C_RIGHT error, %r' % e
    return server._reply_text(fromUser, toUser, msg)


def _do_click_V1001_C_LEFT(server, fromUser, toUser, doc):
    try:
        width = _update_servo_width(USW_SUB)
        msg = 'servo width is %d.' % width
    except Exception, e:
        msg = '_do_click_V1001_C_LEFT error, %r' % e
    return server._reply_text(fromUser, toUser, msg)


def _do_click_SNAPSHOT(server, fromUser, toUser, doc):
    if not _check_user(fromUser):
        return server._reply_text(fromUser, toUser, u'Permission denied…')
    data = None
    err_msg = 'snapshot fail: '
    try:
        data = _take_snapshot('192.168.1.12', 34567, server.client)
    except Exception, e:
        err_msg += str(e)
        return server._reply_text(fromUser, toUser, err_msg)
    return server._reply_image(fromUser, toUser, data.media_id)


def _do_click_V1001_TEMPERATURES(server, fromUser, toUser, doc):

    def _dew_point_fast(t, h):
        import math
        a = 17.27
        b = 237.7
        temp = (a * t) / (b + t) + math.log(h / 100);
        td = (b * temp) / (a - temp);
        return td

    data = '{"name":"environment", "para":{"pin":3}}'
    buf = _arduino_client(data)
    data = eval(buf)
    if type(data) is types.StringType:
        return server._reply_text(fromUser, toUser, data)
    errno = data['errno']
    reply_msg = None
    if errno == 0:
        t = data['resp']['t']
        h = data['resp']['h']
        td = _dew_point_fast(t, h)
        reply_msg = "室内温度: %.2f℃\n室内湿度: %.2f\n室内露点: %.2f" %(t, h, td)
    else:
        reply_msg = buf
    return server._reply_text(fromUser, toUser, reply_msg)


_weixin_click_table = {
    'V1001_USER_LIST'       :   _do_click_V1001_USER_LIST,
    'V1001_LED_ON'          :   _do_click_V1001_LED_ON,
    'V1001_LED_OFF'         :   _do_click_V1001_LED_OFF,
    'V1001_TEMPERATURES'    :   _do_click_V1001_TEMPERATURES,
    'V1001_GOOD'            :   _do_click_V1001_GOOD,
    'V1001_SNAPSHOT'        :   _do_click_SNAPSHOT,
    'V1001_C_LEFT'          :   _do_click_V1001_C_LEFT,
    'V1001_C_RIGHT'         :   _do_click_V1001_C_RIGHT
}


def _do_text_command(server, fromUser, toUser, content):
    temp = content.split(',')
    try:
        return _weixin_text_command_table[temp[0]](server, fromUser, toUser, temp[1:])
    except KeyError, e:
        return server._reply_text(fromUser, toUser, u'Unknow command: '+temp[0])


def _do_text_command_weight(server, fromUser, toUser, para):
    if not _check_user(fromUser):
        return server._reply_text(fromUser, toUser, u'Permission denied…')
    try:
        w = float(para[0])
        data = '{"timestamp":"%s","value":%0.2f}' %(current_time(), w)
        server.yee.datapoint.create(10296, 18659, data)
    except Exception, e:
        return server._reply_text(fromUser, toUser, u'do command fail: %s' %e)
    view = 'http://www.yeelink.net/devices/10296'
    return server._reply_text(fromUser, toUser, u'upload to:'+view)


#def _do_text_command_servo(server, fromUser, toUser, para):
    #try:
        #data = '{"name":"servo","para":{"value":%d}}' %(int(para[0]))
    #except Exception, e:
        #return server._reply_text(fromUser, toUser, str(e))
    #buf = _arduino_client(data)
    #data = eval(buf)
    #errno = None
    #reply_msg = None
    #if type(data) is types.StringType:
        #return server._reply_text(fromUser, toUser, data)
    #errno = data['errno']
    #if errno == 0:
        #reply_msg = "当前角度: %d" %(data['resp']['v'])
    #else:
        #reply_msg = buf
    #return server._reply_text(fromUser, toUser, reply_msg)


def _do_text_command_servo(server, fromUser, toUser, para):
    try:
        data = int(para[0])
    except Exception, e:
        return server._reply_text(fromUser, toUser, str(e))
    width = _update_servo_width(USW_OBS, data)
    reply_msg = "current width %d." %(width)
    return server._reply_text(fromUser, toUser, reply_msg)


def _do_text_command_security(server, fromUser, toUser, para):
    try:
        data = '{"name":"digitalWrite","para":{"pin":5,"value":%d}}' %(int(para[0]))
    except Exception, e:
        return server._reply_text(fromUser, toUser, str(e))
    buf = _arduino_client(data)
    data = eval(buf)
    errno = None
    reply_msg = None
    if type(data) is types.StringType:
        return server._reply_text(fromUser, toUser, data)
    errno = data['errno']
    if errno == 0:
        reply_msg = data['msg']
    else:
        reply_msg = buf
    return server._reply_text(fromUser, toUser, reply_msg)


def _do_text_command_kick_out(server, fromUser, toUser, para):
    msg = 'List is None.'
    wkey = 'wacthers_%s' % server.client.app_id
    try:
        mc = memcache.Client(['192.168.1.12:11211'], debug=0)
        wlist = mc.get(wkey)
        if wlist != None:
            del wlist[int(para[0])]
            mc.replace(wkey, wlist)
            msg = 'Kick out user index=%s' %para
    except Exception, e:
        msg = '_do_text_kick_out error, %r' % e
    return server._reply_text(fromUser, toUser, msg)


def _do_text_command_help(server, fromUser, toUser, para):
    data = "commands:\n"
    for (k, v) in _weixin_text_command_table.items():
        data += "\t%s\n" %(k)
    return server._reply_text(fromUser, toUser, data)


_weixin_text_command_table = {
    'help'                  :   _do_text_command_help,
    'weight'                :   _do_text_command_weight,
    'servo'                 :   _do_text_command_servo,
    'security'              :   _do_text_command_security,
    'kick'                  :   _do_text_command_kick_out
}


class weixinserver:

    def __init__(self):
        self.app_root = os.path.dirname(__file__)
        self.templates_root = os.path.join(self.app_root, 'templates')
        self.render = web.template.render(self.templates_root)
        self.client = WeiXinClient('my_appid', \
                'my_secret', fc=False, path='192.168.1.12:11211')
        self.client.request_access_token()
        self.yee = YeeLinkClient('yee_key')
        #GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(18, GPIO.OUT)

    def _recv_text(self, fromUser, toUser, doc):
        content = doc.find('Content').text
        if content[0] == ',':
            return _do_text_command(self, fromUser, toUser, content[1:])
        reply_msg = content
        return self._reply_text(fromUser, toUser, reply_msg)

    def _recv_event(self, fromUser, toUser, doc):
        event = doc.find('Event').text
        try:
            return _weixin_event_table[event](self, fromUser, toUser, doc)
        except KeyError, e:
            return self._reply_text(fromUser, toUser, u'Unknow event: '+event)

    def _recv_image(self, fromUser, toUser, doc):
        url = doc.find('PicUrl').text
        req = urllib2.Request(url)
        try:
            resp = urllib2.urlopen(req, timeout = 2)
        except urllib2.HTTPError, e:
            return self._reply_text(fromUser, toUser, u'upload fail.')
        view = 'http://www.yeelink.net/devices/10296'
        return self._reply_text(fromUser, toUser, u'upload to:'+view)

    def _recv_voice(self, fromUser, toUser, doc):
        cmd = doc.find('Recognition').text;
        if cmd is None:
            return self._reply_text(fromUser, toUser, u'no Recognition, no command');
        if cmd == u'开灯':
            return _do_click_V1001_LED_ON(self, fromUser, toUser, doc)
        elif cmd == u'关灯':
            return _do_click_V1001_LED_OFF(self, fromUser, toUser, doc)
        elif cmd == u'温度':
            return _do_click_V1001_TEMPERATURES(self, fromUser, toUser, doc)
        elif cmd == u'照片':
            return _do_click_SNAPSHOT(self, fromUser, toUser, doc)
        else:
            return self._reply_text(fromUser, toUser, u'Unknow command: ' + cmd);

    def _recv_video(self, fromUser, toUser, doc):
        pass

    def _recv_location(self, fromUser, toUser, doc):
        pass

    def _recv_link(self, fromUser, toUser, doc):
        pass

    def _reply_text(self, toUser, fromUser, msg):
        return self.render.reply_text(toUser, fromUser, int(time.time()), msg)

    def _reply_image(self, toUser, fromUser, media_id):
        return self.render.reply_image(toUser, fromUser, int(time.time()), media_id)

    def _reply_news(self, toUser, fromUser, title, descrip, picUrl, hqUrl):
        return self.render.reply_news(toUser, fromUser, int(time.time()), title, descrip, picUrl, hqUrl)

    def GET(self):
        data = web.input()
        if _check_hash(data):
            return data.echostr

    def POST(self):
        str_xml = web.data()
        doc = etree.fromstring(str_xml)
        msgType = doc.find('MsgType').text
        fromUser = doc.find('FromUserName').text
        toUser = doc.find('ToUserName').text
        #print 'from:%s-->to:%s' %(fromUser, toUser)
        if msgType == 'text':
            return self._recv_text(fromUser, toUser, doc)
        if msgType == 'event':
            return self._recv_event(fromUser, toUser, doc)
        if msgType == 'image':
            return self._recv_image(fromUser, toUser, doc)
        if msgType == 'voice':
            return self._recv_voice(fromUser, toUser, doc)
        if msgType == 'video':
            return self._recv_video(fromUser, toUser, doc)
        if msgType == 'location':
            return self._recv_location(fromUser, toUser, doc)
        if msgType == 'link':
            return self._recv_link(fromUser, toUser, doc)
        else:
            return self._reply_text(fromUser, toUser, u'Unknow msg:' + msgType)


#application = web.application(_URLS, globals()).wsgifunc()
application = web.application(_URLS, globals())

if __name__ == "__main__":
    application.run()
