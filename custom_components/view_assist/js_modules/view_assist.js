export async function hass_base_el() {
  await Promise.race([
    customElements.whenDefined("home-assistant"),
    customElements.whenDefined("hc-main"),
  ]);

  const element = customElements.get("home-assistant")
    ? "home-assistant"
    : "hc-main";

  while (!document.querySelector(element))
    await new Promise((r) => window.setTimeout(r, 100));
  return document.querySelector(element);
}

export async function hass() {
  const base = await hass_base_el();
  while (!base.hass) await new Promise((r) => window.setTimeout(r, 100));
  return base.hass;
}

function strftime(sFormat, date) {
  if (!(date instanceof Date)) date = new Date();
  var nDay = date.getDay(),
    nDate = date.getDate(),
    nMonth = date.getMonth(),
    nYear = date.getFullYear(),
    nHour = date.getHours(),
    aDays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
    aMonths = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
    aDayCount = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334],
    isLeapYear = function() {
      if ((nYear&3)!==0) return false;
      return nYear%100!==0 || nYear%400===0;
    },
    getThursday = function() {
      var target = new Date(date);
      target.setDate(nDate - ((nDay+6)%7) + 3);
      return target;
    },
    zeroPad = function(nNum, nPad) {
      return ('' + (Math.pow(10, nPad) + nNum)).slice(1);
    };
  return sFormat.replace(/%[a-z]/gi, function(sMatch) {
    return {
      '%a': aDays[nDay].slice(0,3),
      '%A': aDays[nDay],
      '%b': aMonths[nMonth].slice(0,3),
      '%B': aMonths[nMonth],
      '%c': date.toUTCString(),
      '%C': Math.floor(nYear/100),
      '%d': zeroPad(nDate, 2),
      '%e': nDate,
      '%F': date.toISOString().slice(0,10),
      '%G': getThursday().getFullYear(),
      '%g': ('' + getThursday().getFullYear()).slice(2),
      '%H': zeroPad(nHour, 2),
      '%I': zeroPad((nHour+11)%12 + 1, 2),
      '%j': zeroPad(aDayCount[nMonth] + nDate + ((nMonth>1 && isLeapYear()) ? 1 : 0), 3),
      '%k': '' + nHour,
      '%l': (nHour+11)%12 + 1,
      '%m': zeroPad(nMonth + 1, 2),
      '%M': zeroPad(date.getMinutes(), 2),
      '%p': (nHour<12) ? 'AM' : 'PM',
      '%P': (nHour<12) ? 'am' : 'pm',
      '%s': Math.round(date.getTime()/1000),
      '%S': zeroPad(date.getSeconds(), 2),
      '%u': nDay || 7,
      '%V': (function() {
              var target = getThursday(),
                n1stThu = target.valueOf();
              target.setMonth(0, 1);
              var nJan1 = target.getDay();
              if (nJan1!==4) target.setMonth(0, 1 + ((4-nJan1)+7)%7);
              return zeroPad(1 + Math.ceil((n1stThu-target)/604800000), 2);
            })(),
      '%w': '' + nDay,
      '%x': date.toLocaleDateString(),
      '%X': date.toLocaleTimeString(),
      '%y': ('' + nYear).slice(2),
      '%Y': nYear,
      '%z': date.toTimeString().replace(/.+GMT([+-]\d+).+/, '$1'),
      '%Z': date.toTimeString().replace(/.+\((.+?)\)$/, '$1')
    }[sMatch] || sMatch;
  });
}

class Clock extends HTMLElement {
  static observedAttributes = ["server_time", "format"];

  constructor() {
    super();
    this.server_time = true;
  }

  connectedCallback() {
    const shadow = this.shadowRoot || this.attachShadow({ mode: 'open' });
    // Create span
    this.shadowRoot.innerHTML = '';
    const el = document.createElement("span");
    el.setAttribute("class", "clock");
    shadow.appendChild(el);


    if (this.hasAttribute("server_time")) this.server_time = this.getAttribute("server_time");

    this.run_clock(el);
  }

  display_time(el) {

    const dt_now = new Date();
    var format = this.getAttribute("format") ? this.getAttribute("format") : '%H:%M'

    if (this.server_time) {
      el.textContent = strftime(format, new Date(dt_now.getTime() + window.viewassist.server_time_delta));
    } else {
      el.textContent = strftime(format,dt_now);
    }
  }

  run_clock(el) {
    var t = this;
    t.display_time(el);
    const x = setInterval(function () {
      t.display_time(el);
    }, 1000);
  }
}

class CountdownTimer extends HTMLElement {
  static observedAttributes = ["expires", "server_time", "show_negative", "no_timer_text", "expired_text"];

  constructor() {
    super();
    this.expires = 0;
    this.server_time = true;
    this.show_negative = true;
    this.expired_text = '';
    this.no_timer_text = '';
    this.interval_timer = null;
  }

  connectedCallback() {
    const shadow = this.shadowRoot || this.attachShadow({ mode: 'open' });
    // Create span
    this.shadowRoot.innerHTML = '';
    const el = document.createElement("div");
    el.setAttribute("class", "countdown");
    shadow.appendChild(el);



    this.expires = this.getAttribute("expires");
    if (this.hasAttribute("server_time")) this.server_time = this.getAttribute("server_time");
    if (this.hasAttribute("show_negative")) this.show_negative = this.getAttribute("show_negative");
    if (this.hasAttribute("no_timer_text")) this.no_timer_text = this.getAttribute("no_timer_text");
    if (this.hasAttribute("expired_text")) this.expired_text = this.getAttribute("expired_text");

    this.start_timer(el);
  }

  disconnectedCallback() {
    clearInterval(this.interval_timer);
  }

  display_countdown(el) {
    let dt_now = new Date();
    if (this.server_time) {
      // Use now plus server time delta to compare expiry to
      dt_now = new Date(dt_now.getTime() + window.viewassist.server_time_delta);
    }

    const expire = new Date(this.expires).getTime();

    // Find the distance between now and the count down date
    let distance = (expire - dt_now) / 1000;
    let disp_distance = Math.abs(Math.round(distance))

    // Time calculations for days, hours, minutes and seconds
    let days = Math.floor(disp_distance / (60 * 60 * 24));
    let hours = String(Math.floor((disp_distance % (60 * 60 * 24)) / (60 * 60))).padStart(2,'0');
    let minutes = String(Math.floor((disp_distance % (60 * 60)) / (60))).padStart(2,'0');
    let seconds = String(Math.floor(disp_distance % (60))).padStart(2,'0');

    // Display the result in the element
    let sign = Math.round(distance) < 0 ? '-':'';
    if (days) {
      el.textContent = sign + days + "d " + hours + ":" + minutes + ":" + seconds;
    } else {
      el.textContent = sign + hours + ":" + minutes + ":" + seconds;
    }
    return distance
  }

  start_timer(el) {
    if (this.expires != 0) {
      var t = this;
      t.display_countdown(el)
      this.interval_timer = setInterval(function () {
        var distance = t.display_countdown(el);
        if (!t.show_negative && distance < 0) {
          clearInterval(this.interval_timer);
          el.textContent = t.expired_text;
        }
      }, 500);
    } else {
      if (typeof x !== 'undefined') { clearInterval(this.interval_timer) };
      el.textContent = this.no_timer_text;
    }
  }
}


class ViewAssist {
  constructor(hass) {
    this._hass = hass
    this.va_entity = '';
    this.initializeWhenReady();
    this.server_time_delta = 0;
  }

  async initializeWhenReady(attempts = 0) {
    if (attempts > 50) {
      console.log("Failed to initialize after 50 attempts");
      return;
    }

    try {
      await this.set_va_entity();
      await this.set_time_delta();

      console.info(
        `%cVIEW ASSIST ${version} IS INSTALLED
          %cView Assist Entity: ${this.va_entity}
          Time Delta: ${this.server_time_delta}`,
          "color: green; font-weight: bold",
          ""
      );


      const bc = await Promise.resolve(customElements.whenDefined("button-card"))
      if (!bc) {
        throw new Error("No button-card element");
      }

      customElements.define("viewassist-countdown", CountdownTimer)
      customElements.define("viewassist-clock", Clock)

      // Update time delta
      var t = this;
      const delta = setInterval(function () {
        t.set_time_delta();
      }, 300 * 1000);

    } catch (e) {
      console.log("Initialization retry:", e.message);
      setTimeout(() => this.initializeWhenReady(attempts + 1), 100);
    }
  }

  async set_va_entity() {
    this.va_entity = await this._hass.callWS({
      type: 'view_assist/get_entity_id',
      browser_id: localStorage.getItem("browser_mod-browser-id")
    })
    localStorage.setItem("view_assist_sensor", this.va_entity);

  }

  async set_time_delta() {
    const delta = await this._hass.callWS({
      type: 'view_assist/get_server_time_delta',
      epoch: new Date().getTime()
    })
    this.server_time_delta = delta;
  }
}


const version = "1.0.2"

// Get the view asssit entity for this browser id and save in local storage


// Initialize when core web components are ready
const ha = await hass();

Promise.all([
  customElements.whenDefined("home-assistant"),
  customElements.whenDefined("hui-view")
]).then(() => {
  window.viewassist = new ViewAssist(ha);
});
