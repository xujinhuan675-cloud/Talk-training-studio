<template>
  <div v-if="!item.hidden">
    <template v-if="hasOneShowingChild(item.children,item) && (!onlyOneChild.children||onlyOneChild.noShowingChildren)&&!item.alwaysShow">
      <app-link v-if="onlyOneChild.meta" :to="resolvePath(onlyOneChild.path)">
        <el-menu-item :index="resolvePath(onlyOneChild.path)" :class="{'submenu-title-noDropdown':!isNest}">
          <item :icon="onlyOneChild.meta.icon||(item.meta&&item.meta.icon)" :title="onlyOneChild.meta.title" />
          <span v-if="item.meta.xsyIcon" class="xsy_icon"></span>
          <span v-if="item.meta.tjIcon" class="tjIcon"></span>
          <span v-if="item.meta.plIcon" class="plIcon"></span>
        </el-menu-item>

      </app-link>
    </template>

    <el-submenu v-else ref="subMenu" :index="resolvePath(item.path)" popper-append-to-body>
      <template slot="title">
        <item v-if="item.meta" :icon="item.meta && item.meta.icon" :title="item.meta.title" />
        <div class="isNew_tag" v-if="item.meta.isNew">
          <img src="https://daqiangui-web.oss-cn-shanghai.aliyuncs.com/statics/aiChat/images/new.png" alt="">
        </div>
        <!-- <div class="is1212_tag" v-if="item.meta.is1212">
          <img src="../../../assets/images/icong1212.png" alt="">
        </div> -->
      </template>
      <sidebar-item
        v-for="child in item.children"
        :key="child.path"
        :is-nest="true"
        :item="child"
        :base-path="resolvePath(child.path)"
        class="nest-menu"
      />
    </el-submenu>
  </div>
</template>

<script>
import path from 'path'
import { isExternal } from '@/utils/validate'
import Item from './Item'
import AppLink from './Link'
import FixiOSBug from './FixiOSBug'

export default {
  name: 'SidebarItem',
  components: { Item, AppLink },
  mixins: [FixiOSBug],
  props: {
    // route object
    item: {
      type: Object,
      required: true
    },
    isNest: {
      type: Boolean,
      default: false
    },
    basePath: {
      type: String,
      default: ''
    }
  },
  data() {
    // To fix https://github.com/PanJiaChen/vue-admin-template/issues/237
    // TODO: refactor with render function
    this.onlyOneChild = null
    return {}
  },
  methods: {
    hasOneShowingChild(children = [], parent) {
      const showingChildren = children.filter(item => {
        if (item.hidden) {
          return false
        } else {
          // Temp set(will be used if only has one showing child)
          this.onlyOneChild = item
          return true
        }
      })

      // When there is only one child router, the child router is displayed by default
      if (showingChildren.length === 1) {
        return true
      }

      // Show parent if there are no child router to display
      if (showingChildren.length === 0) {
        this.onlyOneChild = { ... parent, path: '', noShowingChildren: true }
        return true
      }

      return false
    },
    resolvePath(routePath) {
      if (isExternal(routePath)) {
        return routePath
      }
      if (isExternal(this.basePath)) {
        return this.basePath
      }
      return path.resolve(this.basePath, routePath)
    }
  }
}
</script>


<style scoped lang="scss">
.nest-menu li{
  padding-left: 52px!important;
}
::v-deep{
  
  .isNew_tag{
    display: inline;
    position: relative;
    img{
      top: -10px;
      left: 5px;
      position: relative;
      width: 30px;
      margin-right: 10px;
    }
  }
  .is1212_tag{
    display: inline;
    position: relative;
    img{
      top: -10px;
      left: 5px;
      position: relative;
      width: 50px;
    }
  }
}
</style>
<style lang="scss" scoped>
  .hideSidebar .isNew_tag{
    display: none;
  }
  .xsy_icon{
    width: 60px;
    height: 24px;
    background: url(https://daqiangui-web.oss-cn-shanghai.aliyuncs.com/statics/qudao/images/xs_nav_icon.png) no-repeat;
    background-size: 100% 100%;
    -webkit-background-size: 100% 100%;
    position: absolute;
    top: 50%;
    left: 65%;
    transform: translate(-50%,-50%);
    -webkit-transform: translate(-50%,-50%);
  }
  .el-menu--vertical .xsy_icon{
    left: 70%;
  }
  .tjIcon,.plIcon{
    width: 41px;
    height: 19px;
    background: url(https://daqiangui-web.oss-cn-shanghai.aliyuncs.com/statics/qudao/images/smartTj_nav_icon.png) no-repeat;
    background-size: 100% 100%;
    -webkit-background-size: 100% 100%;
    position: absolute;
    top: 50%;
    left: 65%;
    transform: translate(-50%,-50%);
    -webkit-transform: translate(-50%,-50%);
  }
  .plIcon{
    background: url(https://daqiangui-web.oss-cn-shanghai.aliyuncs.com/statics/qudao/images/smartTrial_icon.png) no-repeat;
    background-size: 100% 100%;
    -webkit-background-size: 100% 100%;
  }
  .el-menu--vertical .tjIcon,.el-menu--vertical .plIcon{
    left: 70%;
  }
</style>