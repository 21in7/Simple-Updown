<template>
  <div id="app">
    <h1>파일 업로드 및 다운로드 서비스</h1>
    <router-link to="/">파일 업로드</router-link>
    <router-link to="/files">파일 목록</router-link>
    <router-view></router-view>
  </div>
</template>

<script>


export default {
  name: 'App'
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