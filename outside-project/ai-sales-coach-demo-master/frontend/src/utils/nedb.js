/**
 * NeDB封装工具类（内置ID+用户名，无需每次传参）
 * Vue2局部使用，自动注入用户标识，简化增删改查
 */
import Datastore from 'nedb';
// import { localStorageStore } from 'nedb/lib/stores/localStorage';

class NeDBUtil {
  /**
   * 构造函数：初始化时传入用户信息（全局生效，无需重复传）
   * @param {Object} options 配置项
   * @param {String} options.storageKey localStorage存储key（区分页面）
   * @param {String} options.userName 用户名（全局内置，无需每次传）
   * @param {String/Number} options.userId 用户ID（可选，默认自动生成）
   */
  constructor(options = {}) {
    // 基础配置
    this.storageKey = options.storageKey || 'nedb-default-key';
    // 内置用户信息（全局生效）
    this.userName = options.userName || 'default-user'; // 用户名，初始化时传入
    this.userId = options.userId || `user_${Date.now()}_${Math.floor(Math.random() * 1000)}`; // 用户ID（默认自动生成）
    
    this.db = null;
    this.initDB(); // 初始化数据库
  }

  /**
   * 初始化NeDB实例
   */
  initDB() {
    this.db = new Datastore({
     //  store: localStorageStore,
      filename: this.storageKey,
      autoload: true
    });

    this.db.loadDatabase((err) => {
      if (err) console.error(`NeDB(${this.storageKey})初始化失败：`, err);
      else console.log(`NeDB初始化成功，当前用户：${this.userName}`);
    });
  }

  /**
   * 新增数据（自动注入ID+用户名，无需手动传）
   * @param {Object} data 业务数据（仅传非用户/非ID的字段，如age/phone等）
   * @returns {Promise} 新增结果
   */
  insert(data) {
    return new Promise((resolve, reject) => {
      if (!this.db) reject('NeDB实例未初始化');
      
      // 自动拼接：唯一ID + 内置用户名 + 用户ID + 业务数据
      const insertData = {
        id: `data_${Date.now()}_${Math.floor(Math.random() * 10000)}`, // 自动生成唯一数据ID
        userId: this.userId, // 内置用户ID
        userName: this.userName, // 内置用户名
        createTime: new Date().toLocaleString(), // 自动生成创建时间
        ...data // 业务数据（如age/phone等，无需传id/userName）
      };

      this.db.insert(insertData, (err, doc) => {
        if (err) reject(`新增失败：${err.message}`);
        else resolve(doc); // 返回包含自动注入字段的完整数据
      });
    });
  }

  /**
   * 查询当前用户的所有数据（无需传用户条件）
   * @param {Object} options 可选配置：sort/skip/limit
   * @returns {Promise} 查询结果
   */
  findMyData(options = {}) {
    return new Promise((resolve, reject) => {
      if (!this.db) reject('NeDB实例未初始化');
      
      // 默认查询当前用户的所有数据，无需传userId/userName
      let cursor = this.db.find({ userId: this.userId });
      if (options.sort) cursor = cursor.sort(options.sort);
      if (options.skip) cursor = cursor.skip(options.skip);
      if (options.limit) cursor = cursor.limit(options.limit);

      cursor.exec((err, docs) => {
        if (err) reject(`查询失败：${err.message}`);
        else resolve(docs);
      });
    });
  }

  /**
   * 修改当前用户的指定数据（仅传数据ID和要修改的字段，无需传用户信息）
   * @param {String} dataId 要修改的数据ID（仅传ID）
   * @param {Object} updateData 要修改的业务数据（如{age: 28}）
   * @returns {Promise} 修改结果
   */
  updateMyData(dataId, updateData) {
    return new Promise((resolve, reject) => {
      if (!this.db) reject('NeDB实例未初始化');
      
      // 自动拼接：仅修改当前用户下的该条数据，无需传用户条件
      this.db.update(
        { id: dataId, userId: this.userId }, // 自动关联当前用户+数据ID
        { $set: { ...updateData, updateTime: new Date().toLocaleString() } }, // 自动注入修改时间
        { multi: false },
        (err, numReplaced) => {
          if (err) reject(`修改失败：${err.message}`);
          else resolve(`成功修改 ${numReplaced} 条数据`);
        }
      );
    });
  }

  /**
   * 删除当前用户的指定数据（仅传数据ID，无需传用户信息）
   * @param {String} dataId 要删除的数据ID
   * @returns {Promise} 删除结果
   */
  removeMyData(dataId) {
    return new Promise((resolve, reject) => {
      if (!this.db) reject('NeDB实例未初始化');
      
      // 自动关联当前用户，仅删除自己的这条数据
      this.db.remove(
        { id: dataId, userId: this.userId },
        { multi: false },
        (err, numRemoved) => {
          if (err) reject(`删除失败：${err.message}`);
          else resolve(`成功删除 ${numRemoved} 条数据`);
        }
      );
    });
  }

  /**
   * 清空当前用户的所有数据（无需传参）
   * @returns {Promise} 清空结果
   */
  clearMyData() {
    return new Promise((resolve, reject) => {
      if (!this.db) reject('NeDB实例未初始化');
      
      // 仅清空当前用户的数据，不影响其他用户
      this.db.remove(
        { userId: this.userId },
        { multi: true },
        (err, numRemoved) => {
          if (err) reject(`清空失败：${err.message}`);
          else resolve(`成功清空 ${numRemoved} 条数据`);
        }
      );
    });
  }

  // 【可选】保留通用方法（如需操作所有用户数据时使用）
  findAll(query = {}, options = {}) {
    return new Promise((resolve, reject) => {
      if (!this.db) reject('NeDB实例未初始化');
      let cursor = this.db.find(query);
      if (options.sort) cursor = cursor.sort(options.sort);
      if (options.skip) cursor = cursor.skip(options.skip);
      if (options.limit) cursor = cursor.limit(options.limit);
      cursor.exec((err, docs) => resolve(docs));
    });
  }
}

export default NeDBUtil;