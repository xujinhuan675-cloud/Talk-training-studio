import axios from 'axios'
import { getToken } from '@/utils/auth'
import { Loading,Message } from 'element-ui'
import Qs from 'qs'
let baseUrl = process.env.NODE_ENV !== 'development' ? window.location.origin : '/api'

import moment from 'moment'

// 下载xlsx文件流
axios.defaults.transformRequest = [function (data) {
	if(data instanceof FormData){
		//解决qs上传文件格式的会被过滤
		return data
	}else{
		//处理成formDate格式
		return Qs.stringify(data)
	}

}]

let loadinginstace
export function baasRequest(url, body, name, method = 'post',fileType='xls') {
	loadinginstace = Loading.service({
		// text: 'Loading…',
		fullscreen: true
	})
	
	axios({
		method: method,
		url: baseUrl + url,
		headers: {
			'Manage-Token': getToken()
		},
		responseType: 'blob',
		...body
	}).then(res => {
			// const date = new Date();
			const fliName = timeDefault();
			const blob = new Blob([res.data], { type: 'multipary/form-data' });
			// console.log(fliName)
			if (window.navigator && window.navigator.msSaveOrOpenBlob) {
				window.navigator.msSaveOrOpenBlob(blob, `${name}-${fliName}.${fileType}`);
			} else {
				const link = document.createElement('a');
				link.style.display = 'none';
				link.href = URL.createObjectURL(blob);
				link.setAttribute('download', `${name}-${fliName}.${fileType}`);
				document.body.appendChild(link);
				link.click();
				document.body.removeChild(link);
			}
			loadinginstace.close()
		}).catch(() => {
			// tips.message('error', '系统失联，请稍后！！！')
			Message({
				message:'系统失联，请稍后！！！',
				type: 'error',
				duration: 5 * 1000
			   })
			loadinginstace.close()
		})
}




let timeDefault = ()=> {
	return moment(moment().valueOf()).format('YYYY-MM-DD HH-mm-ss')

   }
