<template>
  <div id="app">
    <header>
      <h1>파일 업로드 및 다운로드 서비스</h1>
      <nav class="main-nav">
        <router-link to="/" class="nav-link" active-class="active">
          <i class="nav-icon upload-icon">⬆️</i>
          <span>파일 업로드</span>
        </router-link>
        <router-link to="/files" class="nav-link" active-class="active">
          <i class="nav-icon list-icon">📋</i>
          <span>파일 목록</span>
        </router-link>
      </nav>
    </header>
    <main>
      <router-view></router-view>
    </main>
    <footer>
      <p>© {{ new Date().getFullYear() }} Simple Upload/Download Service</p>
    </footer>
  </div>
</template>

<script>
export default {
  name: 'App'
}
</script>

<style>
:root {
  --primary-color: #4caf50;
  --secondary-color: #2c3e50;
  --accent-color: #f44336;
  --bg-color: #f5f5f5;
  --text-color: #333;
  --border-radius: 6px;
  --box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: 'Noto Sans KR', Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-color: var(--bg-color);
  color: var(--text-color);
  line-height: 1.6;
}

#app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

header {
  background-color: white;
  padding: 20px;
  box-shadow: var(--box-shadow);
}

h1 {
  color: var(--secondary-color);
  text-align: center;
  margin-bottom: 20px;
  font-size: 2rem;
}

.main-nav {
  display: flex;
  justify-content: center;
  gap: 20px;
  padding: 15px 0;
  border-top: 1px solid #eee;
  border-bottom: 1px solid #eee;
  background-color: #fcfcfc;
}

.nav-link {
  display: flex;
  align-items: center;
  padding: 10px 25px;
  text-decoration: none;
  color: var(--text-color);
  font-weight: 500;
  border-radius: var(--border-radius);
  transition: all 0.3s ease;
}

.nav-link:hover {
  background-color: rgba(76, 175, 80, 0.1);
  color: var(--primary-color);
}

.nav-link.active {
  background-color: var(--primary-color);
  color: white;
}

.nav-icon {
  font-style: normal;
  margin-right: 10px;
  font-size: 1.2rem;
}

main {
  flex: 1;
  padding: 30px 20px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

footer {
  text-align: center;
  padding: 20px;
  background-color: var(--secondary-color);
  color: white;
  font-size: 0.9rem;
  margin-top: 50px;
}

@media (max-width: 600px) {
  .main-nav {
    flex-direction: column;
    gap: 10px;
  }
  
  .nav-link {
    width: 100%;
    justify-content: center;
  }
}
</style>