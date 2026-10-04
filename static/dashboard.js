/*
 * HomeLab Portal browser-side logic.
 * HomeLab Portal 浏览器端逻辑。
 *
 * Avoid modern JavaScript syntax for legacy Safari compatibility.
 * 为兼容旧版 Safari，避免使用现代 JavaScript 语法。
 */

var counter = 0;


function updateClock() {

    counter = counter + 1;

    document.getElementById("counter").innerHTML = counter;

    document.getElementById("clock").innerHTML =
        new Date().toLocaleTimeString();
}


updateClock();

setInterval(updateClock, 1000);
