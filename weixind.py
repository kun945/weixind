#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:     weixind.py
# Author:       Liang Cha<my_token@gmail.com>
# CreateDate:   2014-05-15

import os
import web
import time
import types
import hashlib
import memcache
import RPi.GPIO as GPIO
from lxml import etree
from weixin import WeiXinClient
from weixin import APIError


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
    mc = memcache.Client(['127.0.0.1:11211'], debug=0)
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
    cam = ipcam.IPCamClient('10.0.0.101', 11000, 'll', '8898')
    vd = cam.photoaf.get()
    return client.media.upload.file(type='image', pic=vd)


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


def _do_click_V2001_LIST(server, fromUser, toUser, doc):
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


def _do_click_V2001_JOIN(server, fromUser, toUser, doc):
    msg = '你已经加入监控队列。'
    wkey = 'wacthers_%s' % server.client.app_id
    try:
        mc = memcache.Client(['127.0.0.1:11211'], debug=0)
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


def _do_click_V2001_MONITORING(server, fromUser, toUser, doc):
    return server._reply_text(fromUser, toUser, 'monitoring...')


def _do_click_V1001_SOCKET(server, fromUser, toUser, doc):
    if GPIO.input(18):
        GPIO.output(18, GPIO.LOW)
    else:
        GPIO.output(18, GPIO.HIGH)
    if GPIO.input(18):
        reply_msg = '打开状态'
    else:
        reply_msg = '关闭状态'
    return server._reply_text(fromUser, toUser, reply_msg)


def _do_click_V1001_PICTURES(server, fromUser, toUser, doc):
    if not _check_user(fromUser):
        return server._reply_text(fromUser, toUser, u'Permission denied…')
    data = None
    err_msg = 'snapshot fail: '
    try:
        data = _take_snapshot('192.168.1.12', 1101, server.client)
    except Exception, e:
        err_msg += str(e)
        return server._reply_text(fromUser, toUser, err_msg)
    return server._reply_image(fromUser, toUser, data.media_id)


def _do_click_V1001_COMPUTER(server, fromUser, toUser, doc):
    import wol
    ret = False
    reply_msg = '广播失败'
    try:
        ret = wol.wake_on_lan('00:00:00:00:00:00')
    except Exception, e:
        print e
    if ret: reply_msg = '广播成功'
    return server._reply_text(fromUser, toUser, reply_msg)


_weixin_click_table = {
    'V1001_SOCKET'          :   _do_click_V1001_SOCKET,
    'V1001_PICTURES'        :   _do_click_V1001_PICTURES,
    'V1001_COMPUTER'        :   _do_click_V1001_COMPUTER,
    'V2001_MONITORING'      :   _do_click_V2001_MONITORING,
    'V2001_LIST'            :   _do_click_V2001_LIST,
    'V2001_JOIN'            :   _do_click_V2001_JOIN,
}


def _do_text_command(server, fromUser, toUser, content):
    temp = content.split(',')
    try:
        return _weixin_text_command_table[temp[0]](server, fromUser, toUser, temp[1:])
    except KeyError, e:
        return server._reply_text(fromUser, toUser, u'Unknow command: '+temp[0])

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
        mc = memcache.Client(['127.0.0.1:11211'], debug=0)
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
    'security'              :   _do_text_command_security,
    'kick'                  :   _do_text_command_kick_out
}


class weixinserver:

    def __init__(self):
        self.app_root = os.path.dirname(__file__)
        self.templates_root = os.path.join(self.app_root, 'templates')
        self.render = web.template.render(self.templates_root)
        self.client = WeiXinClient('my_appid',
                'my_secret', fc=False, path='127.0.0.1:11211')
        self.client.request_access_token()
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
        return self._reply_text(fromUser, toUser, u'upload to:'+url)

    def _recv_voice(self, fromUser, toUser, doc):
        cmd = doc.find('Recognition').text;
        if cmd is None:
            return self._reply_text(fromUser, toUser, u'no Recognition, no command');
        self._reply_text(fromUser, toUser, u'Unknow command: ' + cmd);

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
        try:
            if _check_hash(data):
                return data.echostr
        except Exception, e:
            print e
            return None

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
