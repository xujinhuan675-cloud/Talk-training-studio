import request from '@/utils/request'

/***********
 *
 * 销冠陪练 - 闯关陪练 相关接口
 *
 ************/

// 维度
const trainingDimensionList = data => request({ url: '/Client/training/dimensionList', method: 'post', data })
const trainingDimensionAdd = data => request({ url: '/Client/training/dimensionAdd', method: 'post', data })
const trainingDimensionEdit = data => request({ url: '/Client/training/dimensionEdit', method: 'post', data })
const trainingDimensionDelete = data => request({ url: '/Client/training/dimensionDelete', method: 'post', data })
const trainingDimensionStatus = data => request({ url: '/Client/training/dimensionStatus', method: 'post', data })

// 场景（dimension_config 由前端 JSON.stringify 后传字符串，后端 json_decode）
const trainingScenarioList = data => request({ url: '/Client/training/scenarioList', method: 'post', data })
const trainingScenarioAdd = data => request({ url: '/Client/training/scenarioAdd', method: 'post', data })
const trainingScenarioEdit = data => request({ url: '/Client/training/scenarioEdit', method: 'post', data })
const trainingScenarioDelete = data => request({ url: '/Client/training/scenarioDelete', method: 'post', data })
const trainingScenarioStatus = data => request({ url: '/Client/training/scenarioStatus', method: 'post', data })
const trainingScenarioListForUser = data => request({ url: '/Client/training/scenarioListForUser', method: 'post', data })

// 演练
const trainingStartSession = data => request({ url: '/Client/training/startSession', method: 'post', data })
const trainingSendMessage = data => request({ url: '/Client/training/sendMessage', method: 'post', data })
const trainingMessageList = data => request({ url: '/Client/training/messageList', method: 'post', data })
const trainingEndSession = data => request({ url: '/Client/training/endSession', method: 'post', data })
const trainingSessionResult = data => request({ url: '/Client/training/sessionResult', method: 'post', data })
const trainingSessionDetail = data => request({ url: '/Client/training/sessionDetail', method: 'post', data })

// 记录 & 统计
const trainingSessionHistory = data => request({ url: '/Client/training/sessionHistory', method: 'post', data })
const trainingLeaderboardTeam = data => request({ url: '/Client/training/leaderboardTeam', method: 'post', data })
const trainingLeaderboardPersonal = data => request({ url: '/Client/training/leaderboardPersonal', method: 'post', data })
const trainingScenarioTeamAvg = data => request({ url: '/Client/training/scenarioTeamAvg', method: 'post', data })
const trainingEmployeeList = data => request({ url: '/Client/training/employeeList', method: 'post', data })
const trainingGroupList = data => request({ url: '/Client/training/groupList', method: 'post', data })

export default {
  trainingDimensionList,
  trainingDimensionAdd,
  trainingDimensionEdit,
  trainingDimensionDelete,
  trainingDimensionStatus,
  trainingScenarioList,
  trainingScenarioAdd,
  trainingScenarioEdit,
  trainingScenarioDelete,
  trainingScenarioStatus,
  trainingScenarioListForUser,
  trainingStartSession,
  trainingSendMessage,
  trainingMessageList,
  trainingEndSession,
  trainingSessionResult,
  trainingSessionDetail,
  trainingSessionHistory,
  trainingLeaderboardTeam,
  trainingLeaderboardPersonal,
  trainingScenarioTeamAvg,
  trainingEmployeeList,
  trainingGroupList
}
