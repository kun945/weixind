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
import base64
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


def _punctuation_clear(ostr):
    '''Clear XML or dict using special punctuation'''
    return str(ostr).translate(None, '\'\"<>&')


def _cpu_and_gpu_temp():
    '''Get from pi'''
    import commands
    try:
        fd = open('/sys/class/thermal/thermal_zone0/temp')
        ctemp = fd.read()
        fd.close()
        gtemp = commands.getoutput('/opt/vc/bin/vcgencmd measure_temp').replace('temp=', '').replace('\'C', '')
    except Exception, e:
        #print e
        return (0, 0)
    return (float(ctemp) / 1000, float(gtemp))



def _json_to_ditc(ostr):
    import json
    try:
        return json.loads(ostr)
    except Exception, e:
        #print e
        return None


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


def _udp_client(addr, data):
    import select
    import socket
    mm = '{"errno":1, "msg":"d2FpdCByZXNwb25zZSB0aW1lb3V0"}'
    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.setblocking(False)
    inputs = [c]
    c.connect(addr)
    c.sendall(data)
    readable, writeable, exceptional = select.select(inputs, [], [], 3)
    try:
        if readable: mm = c.recv(2000)
    except Exception, e:
        mm = '{"errno":1, "msg":"%s"}' %(base64.b64encode(_punctuation_clear(e)))
    finally:
        c.close()
    return mm


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
        #print '_do_event_CLICK: %s' %e
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
        msg = '_do_click_V2001_JOIN error, %r' % e
    return server._reply_text(fromUser, toUser, msg)


def _do_click_V2001_MONITORING(server, fromUser, toUser, doc):
    return server._reply_text(fromUser, toUser, 'monitoring...')


def _do_click_V1001_SOCKET(server, fromUser, toUser, doc):
    GPIO.output(18, GPIO.LOW) if GPIO.input(18) else GPIO.output(18, GPIO.HIGH)
    reply_msg = '打开状态' if GPIO.input(18) else '关闭状态'
    return server._reply_text(fromUser, toUser, reply_msg)


def _do_click_V1001_PICTURES(server, fromUser, toUser, doc):
    if not _check_user(fromUser):
        return server._reply_text(fromUser, toUser, u'Permission denied…')
    data = None
    err_msg = 'snapshot fail: '
    try:
        data = _take_snapshot('192.168.1.12', 1101, server.client)
    except Exception, e:
        err_msg += _punctuation_clear(e)
        return server._reply_text(fromUser, toUser, err_msg)
    return server._reply_image(fromUser, toUser, data.media_id)


def _do_click_V1001_TEMPERATURE(server, fromUser, toUser, doc):
    import dht11
    c, g = _cpu_and_gpu_temp()
    h, t = dht11.read(0)
    reply_msg = u'CPU : %.02f℃\nGPU : %.02f℃\n湿度 : %02.02f\n温度 : %02.02f' %(c, g, h, t)
    return server._reply_text(fromUser, toUser, reply_msg)


def _do_click_V3001_WAKEUP(server, fromUser, toUser, doc):
    import wol
    ret = False
    reply_msg = '广播失败'
    try:
        ret = wol.wake_on_lan('00:00:00:00:00:00')
    except Exception, e:
        #print e
        pass
    if ret: reply_msg = '广播成功'
    return server._reply_text(fromUser, toUser, reply_msg)


def _do_click_V3001_SHUTDOWN(server, fromUser, toUser, doc):
    return _do_text_command_pc(server, fromUser, toUser, ['shutdown -s -t 60'])


def _do_click_V3001_UNDO(server, fromUser, toUser, doc):
    return _do_text_command_pc(server, fromUser, toUser, ['shutdown -a'])


_weixin_click_table = {
    'V1001_SOCKET'          :   _do_click_V1001_SOCKET,
    'V1001_PICTURES'        :   _do_click_V1001_PICTURES,
    'V1001_TEMPERATURE'     :   _do_click_V1001_TEMPERATURE,
    'V2001_MONITORING'      :   _do_click_V2001_MONITORING,
    'V2001_LIST'            :   _do_click_V2001_LIST,
    'V2001_JOIN'            :   _do_click_V2001_JOIN,
    'V3001_WAKEUP'          :   _do_click_V3001_WAKEUP,
    'V3001_SHUTDOWN'        :   _do_click_V3001_SHUTDOWN,
    'V3001_UNDO'            :   _do_click_V3001_UNDO,
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
    buf = _udp_client(('10.0.0.100', 6666), data)
    data = _json_to_ditc(buf)
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


def _do_text_command_pc(server, fromUser, toUser, para):
    if not _check_user(fromUser):
        return server._reply_text(fromUser, toUser, u'Permission denied…')
    if para[0] == 'wol':
        return _do_click_V3001_WAKEUP(server, fromUser, toUser, para)
    print para[0]
    buf = _udp_client(('10.0.0.100', 55555), para[0])
    data = _json_to_ditc(buf)
    if not data:
        reply_msg = _punctuation_clear(buf.decode('gbk'))
    else:
        errno = data['errno']
        reply_msg = data['msg']
        reply_msg = (base64.b64decode(reply_msg)).decode('gbk') if reply_msg \
                else ('运行失败' if errno else '运行成功')
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
    'kick'                  :   _do_text_command_kick_out,
    'pc'                    :   _do_text_command_pc
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
            return self._reply_text(fromUser, toUser, u'Unknow event:%s' %event)

    def _recv_image(self, fromUser, toUser, doc):
        url = doc.find('PicUrl').text
        return self._reply_text(fromUser, toUser, u'upload to:%s' %url)

    def _recv_voice(self, fromUser, toUser, doc):
        import subprocess
        cmd = doc.find('Recognition').text
        mid = doc.find('MediaId').text
        rm = self.client.media.get.file(media_id=mid)
        fd = open('/tmp/test.amr', 'wb')
        fd.write(rm.read())
        fd.close()
        rm.close()
        subprocess.call(['omxplayer', '-o', 'local', '/tmp/test.amr'])
        if cmd is None:
            return self._reply_text(fromUser, toUser, u'no Recognition, no command');
        return self._reply_text(fromUser, toUser, u'Unknow recognition:%s' %cmd);

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
            #print e
            return None

    def POST(self):
        str_xml = web.data()
        doc = etree.fromstring(str_xml)
        msgType = doc.find('MsgType').text
        fromUser = doc.find('FromUserName').text
        toUser = doc.find('ToUserName').text
        print 'from:%s-->to:%s' %(fromUser, toUser)
        #print str_xml
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
