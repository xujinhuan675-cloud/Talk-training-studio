//过表格上方滤筛选框数据

export const filterSearchData = {
     methods: {
          filterSearchData(){
               //过滤筛选条件数据
               let obj = Object.assign(this.pagination || {},{})
               this.formOptions.data.forEach(item=>{
                    if(item.type == 'doubleInput'){
                         //双输入框
                         obj[item.unit[0]] = item.model.startVal || '';
                         obj[item.unit[1]] = item.model.endVal || '';
                         
                    }else if(item.type == 'datePicker' && item.prop == 'datePicker'){
                         //日期范围得
                         obj['start_time'] = item.model[0] || ''
                         obj['end_time'] = item.model[1] || ''
                    }else if(item.type == 'date'){
                         //自定义的时间范围
                         if(item.model && item.model !== ''){
                              obj[item.prop] = item.model.join('~')
                         }else{
                              obj[item.prop] = ''
                         }
                         
                    }else if(item.type == 'Cascader'){
                         //级联的取数组最后一个
                         // obj[item.prop] = item.model[item.model.length - 1 ]
                         
                         if(item.model instanceof Array || !item.model){
                              //返回选择的子级所有id
                              let ids = [];
                              item.model.forEach(item=>{
                                   ids.push(item[item.length - 1]);
                              })                              
                              obj[item.prop] = ids;

                         }
                         else{
                              obj[item.prop] = this.trimStr(String(item.model))
                         }
                    }else{
                         // obj[item.prop] = item.model || ''
                         if(item.model instanceof Array || !item.model){
                              obj[item.prop] = item.model
                         }
                         else{
                              obj[item.prop] = this.trimStr(String(item.model))
                         }
                    }
               })
               return obj
          },
          trimStr(str){
               //去除首尾空格
               return str.replace(/(^\s*)|(\s*$)/g,"");
          }
     },
     
}