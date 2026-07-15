<template>
  <div class="navbar flex flex-y-center">
    <div class="center_pao_ma_deng" style="flex: 1;">
      <div class="nav_right_box flex">
        <p class="flex flex-y-center text_p"> <img src="@/assets/images/guoqi.png" class="icon"> 产品剩余试用天数：<span v-if="limit_day > 0">{{limit_day}}天</span> <span v-else>已过期</span></p>
        <!-- <p class="flex flex-y-center reload_btn">数据刷新<img src="../../assets/images/reload_icon.png" alt=""></p>
        <div class="flex flex-y-center collocation_box">
          <p>开启托管</p>
          <el-switch v-model="collocation" active-color="#5751F4" >
          </el-switch>
        </div> -->
      </div>
    </div>
  </div>
</template>

<script>
import { mapGetters } from 'vuex'

export default {
  // 由父级 Layout 通过 props 传入(避免子组件 bus.$on 订阅时机晚于 emit 导致始终是 -1)
  props: {
    limitDay: {
      type: [Number, String],
      default: -1
    }
  },
  computed: {
    ...mapGetters(['name']),
    limit_day() {
      return Number(this.limitDay)
    }
  },
  data() {
    return {
      collocation: false,//开启托管
      routerName:'',
      is_try:0,//1试用 2 非试用
    }
  },
  created() {
  },
  mounted() {
  },
  methods: {
    myreload() {
      window.location.reload();
    }
  },
  beforeDestroy() {
  },
  watch: {
    $route: {
      handler: function () {
        this.routerName = this.$route.name;
      },
      deep: true
    }
  }
}
</script>

<style lang="scss" scoped>
.navbar {
  height: 48px;
  overflow: hidden;
  position: relative;
  background: #ffffff;
  border-bottom: 1px solid #f3f4f6;
  box-shadow: none;
  display: flex;
  align-items: center;
  justify-content: center;

  .center_pao_ma_deng{
    width: 100%;
  }
  .breadcrumb-container {
    float: left;
  }


  .tips_box {
    //flex: 1;

    // margin-left:10px;
    .tips_text {
      font-size: 14px;
      color: #f73131;
      margin: 5px 0;
    }
  }

  .head_select_box {
    .select_warp {
      width: 100px;
      margin-right: 10px;
      display: inline-block;
    }
  }

  .right-menu {
    margin-right: 16px;

    .name_edit {
      display: flex;
      align-items: center;
      margin-right: 16px;
    }
  }
}


/*.price_btn {
  margin-right: 20px;
  cursor: pointer;
  color: #2845F5;
  font-size: 14px;
  display: flex;
  align-items: center;
  i{
    font-size: 20px;
    margin-right: 5px;
  }
}*/
.nav_right_box {
  width: 100%;
  justify-content: center;
  padding-right: 0;
  .text_p{
    span{
      color: #f73131;
    }
    .icon{
      width: 18px;
      margin-right: 10px;
    }
  }
  .reload_btn {
    font-family: PingFang SC, PingFang SC;
    font-weight: 500;
    font-size: 14px;
    color: #1D2129;
    line-height: 22px;
    white-space: nowrap;

    img {
      width: 24px;
      height: 24px;
      display: block;
      cursor: pointer;
      margin-left: 4px;

      &:hover {
        background: #f8f6ff;
        border-radius: 2px;
      }
    }
  }
  .collocation_box{
    margin-left: 36px;
    p{
      margin-right: 12px;
    }
  }
}
</style>
