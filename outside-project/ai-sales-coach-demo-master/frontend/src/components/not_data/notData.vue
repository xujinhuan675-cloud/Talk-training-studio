<template>
     <div class="no_data_box">
          <img :style="{'width':imgWidth+'px','margin-top':mrTop+'px'}" src="https://daqiangui-web.oss-cn-shanghai.aliyuncs.com/qudao/statics/vue/images/not_img.png" alt="">
          <div>{{ text }} <slot name="dom"></slot></div>
     </div>
</template>

<script>

export default {
     props: {
          //图片宽度
          imgWidth: {
               type: Number,
               default: 298
          },
          text: {
               type: String,
               default: '暂无数据'
          },
          //图片距上边距
          mrTop:{
               type: Number,
               default: 20 
          }
     }
}
</script>

<style lang="scss" scoped>
.no_data_box {
     width: 100%;
     text-align: center;
     img {
          display: block;
          font-size: 0;
          max-width: 100%;
          margin: 20px auto;
     }
     div{
          text-align: center;
          font-size: 14px;
          color: #949DA7;
          margin-bottom: 15px;
     }
}
</style>