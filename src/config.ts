import type {
  AnalyticsConfig,
  CommentConfig,
  GithubConfig,
  Link,
  PhotosConfig,
  PostConfig,
  ProjectConfig,
  Site,
  SkillsShowcaseConfig,
  SocialLink,
  TagsConfig,
} from '~/types'

//--- Readme Page Config ---
export const SITE: Site = {
  title: 'Lin Chun Ho',
  description: 'Lin Chun Ho 的个人技术博客，记录 Java 后端、开源贡献与学习笔记。',
  website: 'https://lymerinblog.z7.web.core.windows.net/',
  lang: 'zh-CN',
  base: '/',
  author: 'Lin Chun Ho',
  ogImage: '/avatar-icon.png',
  transition: false,
  themeAnimation: false,
}

export const HEADER_LINKS: Link[] = [
  {
    name: 'home',
    url: '/',
  },
  {
    name: 'posts',
    url: '/posts',
  },
  {
    name: 'openSource',
    url: '/open-source',
  },
  {
    name: 'about',
    url: '/about',
  },
]

export const FOOTER_LINKS: Link[] = [
  {
    name: 'home',
    url: '/',
  },
  {
    name: 'posts',
    url: '/posts',
  },
  {
    name: 'projects',
    url: '/projects',
  },
  {
    name: 'tags',
    url: '/tags',
  },
  {
    name: 'about',
    url: '/about',
  },
]

// get icon https://icon-sets.iconify.design/
export const SOCIAL_LINKS: SocialLink[] = [
  {
    name: 'GitHub',
    url: 'https://github.com/lymerin',
    icon: 'icon-[mdi--github]',
  },
]

/**
 * SkillsShowcase 配置接口 / SkillsShowcase configuration type
 * @property {boolean} SKILLS_ENABLED  - 是否启用SkillsShowcase功能 / Whether to enable SkillsShowcase features
 * @property {Object} SKILLS_DATA - 技能展示数据 / Skills showcase data
 * @property {string} SKILLS_DATA.direction - 技能展示方向 / Skills showcase direction
 * @property {Object} SKILLS_DATA.skills - 技能展示数据 / Skills showcase data
 * @property {string} SKILLS_DATA.skills.icon - 技能图标 / Skills icon
 * @property {string} SKILLS_DATA.skills.name - 技能名称 / Skills name
 * get icon https://icon-sets.iconify.design/
 */
export const SKILLSSHOWCASE_CONFIG: SkillsShowcaseConfig = {
  SKILLS_ENABLED: true,
  SKILLS_DATA: [
    {
      title: 'Backend & Data',
      direction: 'left',
      skills: [
        { name: 'Java', icon: 'icon-[logos--java]' },
        { name: 'Spring Boot', icon: 'icon-[logos--spring-icon]' },
        { name: 'PostgreSQL', icon: 'icon-[logos--postgresql]' },
        { name: 'MySQL', icon: 'icon-[logos--mysql-icon]' },
        { name: 'Redis', icon: 'icon-[logos--redis]' },
        { name: 'Kafka', icon: 'icon-[logos--kafka-icon]' },
        { name: 'RabbitMQ', icon: 'icon-[logos--rabbitmq-icon]' },
        { name: 'gRPC', icon: 'icon-[logos--grpc]' },
      ],
    },
    {
      title: 'Engineering',
      direction: 'right',
      skills: [
        { name: 'Docker', icon: 'icon-[logos--docker-icon]' },
        { name: 'Linux', icon: 'icon-[logos--linux-tux]' },
        { name: 'Ubuntu', icon: 'icon-[logos--ubuntu]' },
        { name: 'WSL', icon: 'icon-[logos--microsoft-windows-icon]' },
        { name: 'Git', icon: 'icon-[logos--git-icon]' },
        { name: 'Maven', icon: 'icon-[logos--maven]' },
        { name: 'Gradle', icon: 'icon-[logos--gradle]' },
        { name: 'OpenTelemetry', icon: 'icon-[logos--opentelemetry-icon]' },
      ],
    },
    {
      title: 'Tools',
      direction: 'left',
      skills: [
        { name: 'IntelliJ IDEA', icon: 'icon-[logos--intellij-idea]' },
        { name: 'PyCharm', icon: 'icon-[logos--pycharm]' },
        { name: 'VS Code', icon: 'icon-[logos--visual-studio-code]' },
        { name: 'GitHub', icon: 'icon-[mdi--github]' },
        { name: 'Typora', image: '/icons/typora.png' },
      ],
    },
  ],
}

/**
 * GitHub配置 / GitHub configuration
 *
 * @property {boolean} ENABLED - 是否启用GitHub功能 / Whether to enable GitHub features
 * @property {string} GITHUB_USERNAME - GITHUB用户名 / GitHub username
 * @property {boolean} TOOLTIP_ENABLED - 是否开启Tooltip功能 / Whether to enable Github Tooltip features
 */

export const GITHUB_CONFIG: GithubConfig = {
  ENABLED: true,
  GITHUB_USERNAME: 'lymerin',
  TOOLTIP_ENABLED: true,
}

//--- Posts Page Config ---
export const POSTS_CONFIG: PostConfig = {
  title: '文章',
  description: 'Lin Chun Ho 的技术文章与学习记录。',
  introduce: '记录 Java 后端、开源参与、学习笔记与技术思考。',
  author: 'Lin Chun Ho',
  homePageConfig: {
    size: 2,
    type: 'compact',
  },
  postPageConfig: {
    size: 10,
    type: 'image',
    coverLayout: 'right',
  },
  tagsPageConfig: {
    size: 10,
    type: 'time-line',
  },
  ogImageUseCover: false,
  postType: 'metaOnly',
  imageDarkenInDark: true,
  readMoreText: 'Read more',
  prevPageText: 'Previous',
  nextPageText: 'Next',
  tocText: 'On this page',
  backToPostsText: 'Back to Posts',
  nextPostText: 'Next Post',
  prevPostText: 'Previous Post',
  recommendText: 'REC',
  wordCountView: true,
}

export const COMMENT_CONFIG: CommentConfig = {
  enabled: false,
  system: 'none',
}

export const TAGS_CONFIG: TagsConfig = {
  title: '标签',
  description: '按标签浏览文章。',
  introduce: '通过主题和技术标签查找内容。',
}

export const PROJECTS_CONFIG: ProjectConfig = {
  title: '项目',
  description: 'Lin Chun Ho 的项目与实践。',
  introduce: '真实项目将在这里持续补充。',
}

export const PHOTOS_CONFIG: PhotosConfig = {
  title: '照片',
  description: '照片记录。',
  introduce: '暂未公开照片。',
}

export const ANALYTICS_CONFIG: AnalyticsConfig = {
  vercount: {
    enabled: false,
  },
  umami: {
    enabled: false,
    websiteId: '',
    serverUrl: '',
  },
}
