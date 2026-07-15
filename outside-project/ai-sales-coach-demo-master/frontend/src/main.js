import Vue from 'vue'

import 'normalize.css/normalize.css' // A modern alternative to CSS resets

import ElementUI from 'element-ui'
import '@/styles/index.scss' // global css（已含 element-ui 自定义主题）
// import locale from 'element-ui/lib/locale/lang/en' // lang i18n


import App from './App'
import store from './store'
import router from './router'

import '@/icons' // icon
import '@/permission' // permission control

// === H5(/m/*) 子路由共用入口:按需引入 Vant 组件 + H5 设计系统样式 ===
import {
  Tabbar, TabbarItem, NavBar, Button as VanButton, Cell, CellGroup, Tag,
  Field, Dialog, Toast, Loading as VanLoading, PullRefresh, List, Tabs, Tab,
  Empty, ActionSheet, Popup, Picker, Search, Image as VanImage,
  Sticky, Skeleton, NoticeBar, Progress, Checkbox, Form, DropdownMenu, DropdownItem,
  Icon as VanIcon, Overlay, DatetimePicker
} from 'vant'
;[
  Tabbar, TabbarItem, NavBar, VanButton, Cell, CellGroup, Tag,
  Field, VanLoading, PullRefresh, List, Tabs, Tab, Empty,
  ActionSheet, Popup, Picker, Search, VanImage, Sticky, Skeleton,
  NoticeBar, Progress, Checkbox, Form, DropdownMenu, DropdownItem, VanIcon,
  Overlay, DatetimePicker
].forEach(c => Vue.use(c))
Vue.prototype.$toast = Toast
Vue.prototype.$dialog = Dialog
// 注册 Vant Toast,request.js 在 H5 路径下会调用它代替 Element Message
window.__H5_SHOW_ERROR__ = (msg) => Toast.fail({ message: msg, position: 'middle', duration: 2500 })
import '@/h5/styles/h5-design-system.scss'

import PageHeader from '@/components/PageHeader/index.vue'
Vue.component('PageHeader', PageHeader)

// collapse 展开折叠
import CollapseTransition from 'element-ui/lib/transitions/collapse-transition';

Vue.component(CollapseTransition)


// set ElementUI lang to EN
// Vue.use(ElementUI, { locale })
Vue.use(ElementUI)
// 如果想要中文版 element-ui，按如下方式声明
// Vue.use(ElementUI)


// 在main.js中全局注册过滤器
Vue.filter('formatMsDate', function(msTimestamp) {
  // 处理空值、无效值或非毫秒级时间戳（13位数字）
  if (!msTimestamp || typeof msTimestamp !== 'number' || msTimestamp.toString().length !== 13) {
    return ''; // 非有效毫秒时间戳返回空
  }

  const date = new Date(msTimestamp);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  // 提取年月日（用于比较）
  const getDateStr = (d) => {
    return [
      d.getFullYear(),
      String(d.getMonth() + 1).padStart(2, '0'),
      String(d.getDate()).padStart(2, '0')
    ].join('-');
  };

  const targetDateStr = getDateStr(date);
  const yesterdayStr = getDateStr(yesterday);

  // 判断是否为昨天
  // if (targetDateStr === yesterdayStr) {
  //   return '昨天';
  // }  
  // 其余情况返回年月日（格式：YYYY-MM-DD）
  return targetDateStr;
});

Vue.config.productionTip = false

new Vue({
  el: '#app',
  router,
  store,
  render: h => h(App)
})
