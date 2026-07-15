<template>
  <section class="ces-pagination">
     <el-pagination style='display: flex;height: 100%;align-items: center;'
          @current-change="handleCurrentChange"
          @size-change="handleSizeChange"
          layout="total,prev, pager, next,jumper"
          :page-size="pagination.limit"
          :current-page="pagination.page"
          :total="pagination.total"
     ></el-pagination>
</section>
</template>

<script>
export default {
     props:{
          // 分页数据
        pagination:{ type:Object,default:()=>({limit:20,page:1,total:0})},
     },
     data() {
          return {
               
          }
     },
     methods:{
        handleCurrentChange(val){
          this.pagination.page = val;
          this.$emit('handleCurrentChange',val);
        },
        handleSizeChange(val) {
          this.pagination.limit = val;
          this.$emit('handleSizeChange',val);
        },
        
    },
}
</script>

<style scoped>
.ces-pagination{
     margin-top: 20px;
}
</style>