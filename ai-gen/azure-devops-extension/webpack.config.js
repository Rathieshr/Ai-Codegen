const path = require('path');
const { Compilation, sources } = require('webpack');

class EmitHeiHostPagePlugin {
  apply(compiler) {
    compiler.hooks.thisCompilation.tap('EmitHeiHostPagePlugin', (compilation) => {
      compilation.hooks.processAssets.tap(
        { name: 'EmitHeiHostPagePlugin', stage: Compilation.PROCESS_ASSETS_STAGE_ADDITIONAL },
        () => compilation.emitAsset('hei/index.html', new sources.RawSource(`<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HEI Engineering Command Center</title>
  </head>
  <body><div id="root"></div><script src="app.js"></script></body>
</html>`)),
      );
    });
  }
}

module.exports = {
  entry: {
    'hei/app': './src/heiApp.tsx',
    projectIntelligenceTab: './src/projectIntelligenceTab.tsx',
    storyPlannerTab: './src/storyPlannerTab.tsx',
    workItemTab: './src/workItemTab.tsx',
    workItemAction: './src/workItemAction.ts',
    openHeiAction: './src/openHeiAction.ts'
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
  },
  plugins: [new EmitHeiHostPagePlugin()]
};
