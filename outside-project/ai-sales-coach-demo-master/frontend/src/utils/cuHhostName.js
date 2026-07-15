/**
 * 检查当前域名是否匹配预设配置
 * @returns {Object} 包含匹配结果和配置数据的对象
 */
export function includingURL() {
    const currentOrigin = location.origin;
    const configs = [
        {
            href: 'lc001.zhenhuidai.com',
            ico: 'favicon2.ico',
            name: '析客巨效智能',
        },
        {
            href: 'seek-x.cn',
            ico: 'favicon2.ico',
            name: '析客巨效智能',
        }
    ];

    const match = configs.find(item =>
        currentOrigin.includes(item.href) ||
        item.href === currentOrigin
    );

    return {
        hasHref: !!match,
        data: match || {}
    };
}
