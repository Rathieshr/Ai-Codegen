const path = require('path');

module.exports = {
  entry: {
    projectIntelligenceTab: './src/projectIntelligenceTab.tsx',
    storyPlannerTab: './src/storyPlannerTab.tsx',
    workItemTab: './src/workItemTab.tsx',
    workItemAction: './src/workItemAction.ts'
  },
  output: {
    filename: '[name].js',
    path: path.resolve(__dirname, 'dist'),
    clean: true
  },
  resolve: {
    extensions: ['.ts', '.tsx', '.js']
  },
  module: {
    rules: [
      {
        test: /\.tsx?$/,
        use: 'ts-loader',
        exclude: /node_modules/
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader']
      }
    ]
  }
};
