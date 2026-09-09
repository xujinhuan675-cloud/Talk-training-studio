module.exports = {
  extends: ['@commitlint/config-conventional'],
  plugins: [
    {
      rules: {
        'subject-chinese': ({ subject }) => [
          /[\u4e00-\u9fff]/.test(subject || ''),
          'subject 必须包含中文摘要',
        ],
        'body-grouped-ordered-list': ({ body }) => [
          /^\s*\d+\.\s+\S/m.test(body || ''),
          'body 必须包含有序编号分组（例如 "  1. 说明"）',
        ],
      },
    },
  ],
  rules: {
    'type-enum': [
      2,
      'always',
      ['feat', 'fix', 'docs', 'style', 'refactor', 'perf', 'test', 'build', 'ci', 'chore', 'revert', 'i18n'],
    ],
    'type-empty': [2, 'never'],
    'type-case': [2, 'always', 'lower-case'],
    'subject-empty': [2, 'never'],
    'subject-case': [0],
    'subject-chinese': [2, 'always'],
    'subject-full-stop': [0, 'never'],
    'header-max-length': [2, 'always', 120],
    'body-empty': [2, 'never'],
    'body-grouped-ordered-list': [2, 'always'],
  },
};
