#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:     weixind.py
# Author:       chenkun<your_token@gmail.com>
# CreateDate:   2014-05-15

import os
import web
import time
import hashlib
from lxml import etree
from weixin import WeiXinClient


_TOKEN = 'your_token'
_URLS = (
    '/*', 'weixinserver',
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

def _get_user_info(wc):
    req = wc.user.get._get(next_openid = None)
    count = req.count
    total = req.total
    data = req.data
    id_list = data.openid
    while count < total:
        if next_openid in data.openid:
            break
        req = wc.user.get._get(next_openid = None)
        count += req.count
        data = req.data
        next_openid = req.next_openid
        id_list.extend(data.openid)
    info_list = []
    for open_id in id_list:
        req = wc.user.info._get(openid=open_id, lang='zh_CN')
        name ='%s' %(req.nickname)
        place = '%s,%s,%s' %(req.country, req.province, req.city)
        sex = '%s' %(u'男') if (req.sex == 1) else u'女'
        info_list.append({'name':name, 'place':place, 'sex':sex})
    return info_list

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
    user_list = _get_user_info(server.client)
    for user in user_list:
        reply_msg += '%s|%s|%s\n' %(user['name'], user['place'], user['sex'])
    return server._reply_text(fromUser, toUser, reply_msg)

def _do_click_V1001_YELLOW_CHICK(server, fromUser, toUser, doc):
    pass

def _do_click_V1001_GOOD(server, fromUser, toUser, doc):
    pass

_weixin_click_table = {
        'V1001_USER_LIST'       :   _do_click_V1001_USER_LIST,
        'V1001_YELLOW_CHICK'    :   _do_click_V1001_YELLOW_CHICK,
        'V1001_V1001_GOOD'      :   _do_click_V1001_GOOD
}


class weixinserver:

    def __init__(self):
        self.app_root = os.path.dirname(__file__)
        self.templates_root = os.path.join(self.app_root, 'templates')
        self.render = web.template.render(self.templates_root)
        self.client = WeiXinClient('your_appid', \
                'your_secret', fc = False)
        self.client.request_access_token()

    def _recv_text(self, fromUser, toUser, doc):
        content = doc.find('Content').text
        reply_msg = content
        return self._reply_text(fromUser, toUser, reply_msg)

    def _recv_event(self, fromUser, toUser, doc):
        event = doc.find('Event').text
        try:
            return _weixin_event_table[event](self, fromUser, toUser, doc)
        except KeyError, e:
            print '_recv_event: %s' %e
            return server._reply_text(fromUser, toUser, u'Unknow event: '+event)

    def _recv_image(self, fromUser, toUser, doc):
        pass

    def _recv_voice(self, fromUser, toUser, doc):
        pass

    def _recv_video(self, fromUser, toUser, doc):
        pass

    def _recv_location(self, fromUser, toUser, doc):
        pass

    def _recv_link(self, fromUser, toUser, doc):
        pass

    def _reply_text(self, toUser, fromUser, msg):
        return self.render.reply_text(toUser, fromUser, int(time.time()), msg)

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


application = web.application(_URLS, globals()).wsgifunc()
