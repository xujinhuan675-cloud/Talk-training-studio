import API from "@/api";
//测试域名
let testUrl = 'test.motorcycle.daqiangui.com';
//测试环境 ws  其余的 wss
let ws = (location.host == testUrl) ? 'ws://' : 'wss://';
let baseUrl = process.env.NODE_ENV !== 'development' ? (ws + location.host + '/') : 'ws://test.motorcycle.daqiangui.com/';
let credential = localStorage.getItem('credential');

//模拟定时器 解决浏览器切换tab后定时器会被延迟
import { 
    setWorkerTimeout, 
    setWorkerInterval,
    clearWorkerTimer
} from 'set-worker-timer';

import { getCurrentTime} from '@/utils';
//webSocket
export const webVx = {
    data() {
        return {
            webSocket: '',//ws链接
            xtTimer: null,//心跳定时器
            linkNUm: 0,//链接数量
            againLink: null,//
            isFirst: true,//第一次链接
        }
    },
    methods: {
        socketInit()//初始化连接
        {
            let _this = this;
            _this.webSocket = new WebSocket(`${baseUrl}swoole?user_id=${credential}`);
            //链接失败
            _this.webSocket.onerror = function (event) {
                _this.linkNUm++;
                if (_this.linkNUm > 10) {
                    console.log('超出最大连接值');
                    return
                }
                // 5自动重连
                clearWorkerTimer(_this.againLink);
                _this.againLink = setWorkerTimeout(() => {
                    _this.socketInit();
                }, 1000 * 10);
                this.isFirst = true;
            }
            //链接关闭
            _this.webSocket.onclose = function (event) {
                console.log('Socket连接关闭',event);
                clearWorkerTimer(_this.xtTimer);
                _this.isFirst = true;

            }
            //链接成功
            _this.webSocket.onopen = function (event) {
                //关闭非当前的ws链接
                _this.wsSend('{"command":"closeoldws"}');
                clearWorkerTimer(_this.againLink);
                _this.linkNUm = 0;
                clearWorkerTimer(_this.xtTimer);
                _this.xtTimer = setWorkerInterval(_this.HeartBeatCheck, 1000 * 20);//设置心跳
                console.log('连接成功');

            }
            //消息返回
            _this.webSocket.onmessage = _this.DeviceCallback;
        },
        //ws消息回调
        DeviceCallback(event) {
            let msgJsonData = JSON.parse(event.data);
            let type = msgJsonData.type;//type         
            if (type == 'ConversationPushNotice') {
                //设置会话列表
                this.getConversationPushNotice(msgJsonData.data);
            } else if (type == 'HistoryMsgPushNotice') {
                //获取到聊天记录了
                this.SetCurrentChats(msgJsonData.data);
                // console.log(msgJsonData.data);

            } else if (type == 'ChatRoomMembersNotice') {
                //获取到群里陌生人详情了（非好友关系）
                this.ChatRoomMembersNotice(msgJsonData.data);
            } else if (type == 'FriendChangeNotice') {
                //获取到某个成员的详情了 （好友关系）
                this.FriendChangeNotice(msgJsonData.data);
            } else if (type == 'WeChatTalkToFriendNotice') {
                //sdk 微信发信息通知 ok
                //更新会话列表
                this.updataUserList({ ...msgJsonData.data, IsSend: true });
                //更新聊天窗口数据
                this.upChatsList({ ...msgJsonData.data, IsSend: true });

            } else if (type == 'FriendTalkNotice') {
                //好友给你发消息了
                this.updataUserList(msgJsonData.data);
                //更新聊天窗口数据
                this.upChatsList(msgJsonData.data);
                // console.log(msgJsonData.data);

            } else if (type == 'RequestTalkDetailTaskResultNotice') {
                // 图片或视频消息的详细内容结果
                this.RequestTalkDetailTaskResultNotice(msgJsonData.data);
            } else if (type == 'ReplyTypeChangeNotice') {
                // 聊天类型变更
                this.replyTypeChangeNotice(msgJsonData.data);
            } else if (type == 'FriendPushNotice') {
                // 收到通讯录推送了
                this.friendPushNotice(msgJsonData.data);
            }else if (type == 'ForceLogout') {
                // 单点登录挤掉线
                this.forceLogout(msgJsonData.data);                
            }else if (type == 'pong') {
                // 收到通讯录推送了
                // this.friendPushNotice(msgJsonData.data);
                // console.log('心跳回复了',getCurrentTime().timer);
            }else if (type == 'AiMsgReplyNotice') {
                // ai回复收到结果了
                console.log('ai回复收到结果了',msgJsonData.data);    
                this.AiMsgReplyNotice(msgJsonData.data);            
            }
        },
        wsSend(msg) {
            if (this.webSocket && this.webSocket.readyState === WebSocket.OPEN) {
                this.webSocket.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
            } else {
                console.warn('[WS] 连接未就绪，消息已丢弃', this.webSocket?.readyState);
            }
        },
        HeartBeatCheck()//心跳检测
        {
            this.wsSend(JSON.stringify({"msgType":"ping"}));
            // console.log('发送心跳了',getCurrentTime().timer);
        },
        closeWs() {
            this.clearSocket();
            this.webSocket.close();
        },
        clearSocket() {
            //清空状态
            clearWorkerTimer(this.xtTimer);
            clearWorkerTimer(this.againLink);
        }
    }
}



