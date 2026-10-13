// 主题切换 + 通用渲染
(function () {
  // 主题
  const saved = localStorage.getItem("theme");
  if (saved === "light" || saved === "dark") {
    document.documentElement.setAttribute("data-theme", saved);
  }
  window.toggleTheme = function () {
    const cur = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  };

  // 彩蛋：博客板块解锁状态（sessionStorage 存于当前标签页，关掉即失效）
  // 临时功能：删掉本段 + style.css 里对应的隐藏规则即可恢复常规展示
  (function () {
    var KEY = "blogUnlocked";
    function unlocked() {
      try { return sessionStorage.getItem(KEY) === "1"; } catch (e) { return false; }
    }
    if (unlocked()) document.documentElement.classList.add("blog-unlocked");

    window.isBlogUnlocked = unlocked;
    window.unlockBlog = function () {
      try { sessionStorage.setItem(KEY, "1"); } catch (e) {}
      document.documentElement.classList.add("blog-unlocked");
      // 板块隐藏期间 IntersectionObserver 观察不到它，解锁后手动补上 visible
      var sec = document.getElementById("blog");
      if (sec) {
        sec.classList.add("visible");
        sec.querySelectorAll(".reveal").forEach(function (el) { el.classList.add("visible"); });
      }
    };
  })();

  // 当前导航高亮 + 滚动渐入
  document.addEventListener("DOMContentLoaded", function () {
    const path = location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll(".nav-links a[data-page]").forEach(function (a) {
      if (a.getAttribute("data-page") === path) a.classList.add("active");
    });

    // 年份
    const y = document.getElementById("year");
    if (y) y.textContent = new Date().getFullYear();

    // 滚动渐入（reveal）
    var reveals = document.querySelectorAll(".reveal");
    if ("IntersectionObserver" in window && reveals.length) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) {
            e.target.classList.add("visible");
            io.unobserve(e.target);
          }
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -30px 0px" });
      reveals.forEach(function (el) { io.observe(el); });
    } else {
      reveals.forEach(function (el) { el.classList.add("visible"); });
    }
  });
})();

// 文章卡片渲染（首页/列表页共用）
function renderPostCards(containerId, limit) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const posts = window.POSTS.slice(0, limit || window.POSTS.length);
  el.innerHTML = posts.map(function (p, i) {
    return (
      '<div class="card post-card reveal d' + (i % 3) + '">' +
      '<span class="tag">' + p.tag + "</span>" +
      '<h3><a href="post.html?id=' + p.id + '">' + p.title + "</a></h3>" +
      '<div class="excerpt">' + p.excerpt + "</div>" +
      '<div class="meta"><i class="far fa-calendar-alt"></i> ' + p.date + " · " + p.content.length + " 段</div>" +
      "</div>"
    );
  }).join("");
}

// 投资组合：数字格式化
function fmtNav(v) {
  return Number(v).toFixed(4);
}
function fmtPct(v) {
  return (v >= 0 ? "+" : "") + Number(v).toFixed(2) + "%";
}
