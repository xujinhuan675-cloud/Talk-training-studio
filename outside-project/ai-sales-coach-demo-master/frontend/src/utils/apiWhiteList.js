let whiteList = [
     '/Client/brand/getByDomain',
     '/Client/staff/addConfig',
     '/Client/group/editConfig',
     '/Client/chat/getMessageList',
     '/Client/label/lists',
     '/Client/label/getTaskChange',
     '/Client/label/tagRewrite',
     '/Client/label/getTaskList',
     '/Client/summaryTask/getSummaryInfo',
     '/friendCircle/listConfig',
     '/Client/friendCircle/getBigImages',
     '/Client/chat/getMaterialList',
     '/Client/chat/materialListsConfig',
     '/Client/chat/getPackageList',
     // '/Client/chat/msgReplyAi'
     '/Client/feedRecord/getDetail',
     '/Client/feedRecord/qaListsConfig',
     '/Client/feedRecord/getBatchStatus',
     '/Client/chat/wxSessionInfo',

     // AI创作中心：全部接口禁用全局loading，各操作有独立loading状态
     '/Client/aiCreation/submitTask',
     '/Client/aiCreation/getProgress',
     '/Client/aiCreation/getTaskList',
     '/Client/aiCreation/getWorkList',
     '/Client/aiCreation/cancelTask',
     '/Client/aiCreation/deleteWork',
     '/Client/aiCreation/saveToMaterial',
     '/Client/aiCreation/uploadMaterial',
     '/Client/aiCreation/uploadMaterialByUrl',
     '/Client/aiCreation/batchSaveToMaterial',
     '/Client/aiCreation/batchDeleteWork',
     '/Client/aiCreation/getTrashList',
     '/Client/aiCreation/restoreWork',
     '/Client/aiCreation/permanentDeleteWork',

     // 提示词润色：组件内有自己的loading状态，禁用全局loading
     '/Client/promptPolish/submit',
     '/Client/promptPolish/getResult',
     '/Client/remix/getTaskProgress',
     '/Client/remix/generateFullVideo',

     // 小红书：轮询类接口禁用全局loading
     '/Client/xhsAccount/checkQrStatus',
     '/Client/xhsAccount/refreshInfo',
     '/Client/xhsAccount/getPromptOptions',
     '/Client/xhsNote/getAccountOptions',
     '/Client/xhsNote/generateCopy',
     '/Client/xhsNote/getCopyResult',
     '/Client/xhsNote/generateImages',
     '/Client/xhsNote/getImageResult',

     // 工作台 KPI：页面内有骨架屏loading
     '/Client/workspace/kpi',

     // 抖音发布：页面内有独立loading状态
     '/Client/douyinPublish/lists',
     '/Client/douyinPublish/accountList',
     '/Client/douyinPublish/save',
     '/Client/douyinPublish/publish',
     '/Client/douyinPublish/detail',
     '/Client/douyinPublish/delete',
     '/Client/douyinPublish/republish',
     // v1.2 广告脚本：轮询和生成接口禁用全局loading
     '/Client/remix/generateAdScript',
     '/Client/remix/getAdTaskStatus',
     '/Client/remix/optimizeAdScript',
     '/Client/remix/generateAdImages',
     '/Client/remix/regenerateAdImage',
     '/Client/remix/generateAdVideos',
     '/Client/remix/getOutputList',

     // 朋友圈定时发圈：AI轮询接口禁用全局loading
     '/Client/circleTask/aiResult',
     '/Client/circleTask/aiPolish',
     '/Client/circleTask/aiGenerate',

     // 精修接口
     '/Client/remix/refineExport',
     '/Client/remix/getRefineExportStatus',
     '/Client/remix/refineTtsBatch',
     '/Client/remix/saveAdOutput',

     // H5 销冠陪练:用 Vant Toast 自管 loading,禁用全局 Element Loading
     '/Client/training/scenarioListForUser',
     '/Client/training/startSession',
     '/Client/training/sendMessage',
     '/Client/training/messageList',
     '/Client/training/endSession',
     '/Client/training/sessionResult',
     '/Client/training/sessionDetail',
     '/Client/training/sessionHistory',
     '/Client/training/leaderboardTeam',
     '/Client/training/leaderboardPersonal',
     '/Client/training/scenarioTeamAvg',
     '/Client/training/groupList',
     '/Client/training/employeeList',

]

export default whiteList
