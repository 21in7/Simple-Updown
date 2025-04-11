<template>
  <div id="app">
    <h1>파일 업로드 및 다운로드 서비스</h1>
    <Upload />
    <Files />
  </div>
</template>

<script>
import FileUpload from './components/FileUpload.vue';
import FilesList from './components/FilesList.vue';

export default {
  name: 'App',
  components: {
    FileUpload,
    FilesList
  }
}
</script>

<style>
#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
  margin-top: 60px;
}
</style>