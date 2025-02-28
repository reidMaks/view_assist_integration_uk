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

class CountdownTimer extends HTMLElement {
  static observedAttributes = ["expires"];

  constructor() {
    super();
  }

  connectedCallback() {
    //console.log("Custom element added to page.");
    const shadow = this.shadowRoot || this.attachShadow({ mode: 'open' });
    // Create spans
    this.shadowRoot.innerHTML = '';
    const info = document.createElement("span");
    info.setAttribute("class", "info");
    shadow.appendChild(info);


    const expires = this.getAttribute("expires");
    this.start_timer(info, expires);
  }

  disconnectedCallback() {
    this.s
    console.log("Custom element removed from page.");
  }

  adoptedCallback() {
    console.log("Custom element moved to new page.");
  }

  attributeChangedCallback(name, oldValue, newValue) {
    console.log(`Attribute ${name} has changed.`);
  }

  display_countdown(info, expires) {
    // Get today's date and time
    var now = new Date().getTime();
    var expire = new Date(expires).getTime();
    console.log("NOW: " + now + ", EXPIRE: " + expire)

    // Find the distance between now and the count down date
    var distance = expire - now;

    // Time calculations for days, hours, minutes and seconds
    var days = Math.floor(distance / (1000 * 60 * 60 * 24));
    var hours = String(Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))).padStart(2,'0');
    var minutes = String(Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60))).padStart(2,'0');
    var seconds = String(Math.floor((distance % (1000 * 60)) / 1000)).padStart(2,'0');

    // Display the result in the element with id="demo"
    if (days) {
      info.textContent = days + "d " + hours + ":" + minutes + ":" + seconds;
    } else {
      info.textContent = hours + ":" + minutes + ":" + seconds;
    }
    return distance
  }

  start_timer(info, expires) {
    if (expires != 0) {
      var t = this;
      t.display_countdown(info, expires)
      const x = setInterval(function () {
        var distance = t.display_countdown(info, expires);
        if (distance < 0) {
          clearInterval(x);
          info.textContent = "Expired";
        }
      }, 250);
    } else {
      if (typeof x !== 'undefined') { clearInterval(x) };
      info.textContent = "No Timers";
    }
  }
}


class ViewAssist {
  constructor(hass) {
    this.hass = hass
    this.initializeWhenReady();
  }

  async initializeWhenReady(attempts = 0) {
    if (attempts > 50) {
      console.log("Failed to initialize after 50 attempts");
      return;
    }

    try {
      await this.set_va_entity();

      const bc = await Promise.resolve(customElements.whenDefined("button-card"))
      if (!bc) {
        throw new Error("No button-card element");
      }

      customElements.define("viewassist-countdown", CountdownTimer)

    } catch (e) {
      console.log("Initialization retry:", e.message);
      setTimeout(() => this.initializeWhenReady(attempts + 1), 100);
    }
  }

  async set_va_entity() {
    const va_entity = await this.hass.callWS({
      type: 'view_assist/get_entity_id',
      browser_id: localStorage.getItem("browser_mod-browser-id")
    })
    localStorage.setItem("view_assist_sensor", va_entity);

    console.info(
      `%cVIEW ASSIST ${version} IS INSTALLED
        %cView Assist Entity: ${va_entity}`,
        "color: green; font-weight: bold",
        ""
    );

  }
}


const version = "1.0.1"

// Get the view asssit entity for this browser id and save in local storage


// Initialize when core web components are ready
const ha = await hass();

Promise.all([
  customElements.whenDefined("home-assistant"),
  customElements.whenDefined("hui-view")
]).then(() => {
  window.ViewAssist = new ViewAssist(ha);
});
