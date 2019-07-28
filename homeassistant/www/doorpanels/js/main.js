var myIP = null;
var hawsConn = null;
var currentCode = '';
var inputTimeout = null;
var groupStates = {};
var inDuress = null;

import {
  Auth,
  callService,
  createConnection,
  subscribeEntities,
  getStates,
  getUser,
  ERR_HASS_HOST_REQUIRED
} from "./haws.es.js";

import {
  apiToken,
  hassBaseUrl
} from "./local_apitoken.js"

(async () => {
  $('#status').html('Connecting to ' + hassBaseUrl + '...');
  console.log('Connecting to ' + hassBaseUrl + '...');
  let auth = new Auth({
    access_token: apiToken,
    // Set expires to very far in the future
    expires: new Date(new Date().getTime() + 1e11),
    hassUrl: hassBaseUrl
  });
  myIP = await getLocalIP();
  $('#status').html('Connecting to ' + hassBaseUrl + '...<br />my IP: ' + myIP);
  console.log('Connecting to ' + hassBaseUrl + '...<br />my IP: ' + myIP);
  const connection = await createConnection({ auth });
  hawsConn = connection;
  getUser(connection).then(
    user => {
      $('#status').html('Connected to ' + hassBaseUrl + ' as ' + user + '.<br />my IP: ' + myIP);
      console.log('Connected to ' + hassBaseUrl + ' as ' + user.name + '.<br />my IP: ' + myIP);
    }
  );
  connection.subscribeEvents(handleEvent);
  getStates(connection).then(states => {
    states.forEach(function(s) {
      if (s.entity_id == 'input_select.alarmstate') { handleAlarmState(s.state); }
      if (s.entity_id == 'input_boolean.alarm_duress') { handleAlarmDuress(s.state); }
      if (s.entity_id.startsWith('group.')) {
        var groupName = s.entity_id.split(".")[1];
        groupStates[groupName] = s.state;
        handleLightStateChange(groupName, s.state);
      }
    });
  });

  // To play from the console
  window.auth = auth;
  window.connection = connection;
})();

/** Callback on the HAWS connection; called for all events.
 *
 * Param is an Event object that includes old and new states.
 */
function handleEvent(e) {
  if(e.event_type == 'state_changed') {
    if(e.data.entity_id == 'input_select.alarmstate') { handleAlarmState(e.data.new_state.state); }
    if(e.data.entity_id.startsWith('group.')) {
      var groupName = e.data.entity_id.split(".")[1];
      groupStates[groupName] = e.data.new_state.state;
      handleLightStateChange(groupName, e.data.new_state.state);
    }
    if(e.data.entity_id == 'input_boolean.arming_away') {
      if(e.data.new_state.state == 'on') {
        $('#arming_away').show();
      } else {
        $('#arming_away').hide();
      }
    }
    if(e.data.entity_id == 'input_boolean.trigger_delay') {
      if(e.data.new_state.state == 'on') {
        $('body').addClass('alarm-triggered');
      } else {
        $('body').removeClass('alarm-triggered');
      }
    }
    if(e.data.entity_id == 'input_boolean.alarm_duress') { handleAlarmDuress(e.data.new_state.state); }
  }
}

/**
 * Handle state change for a light.
 */
function handleLightStateChange(groupName, newState) {
  console.log('handleLightStateChange(%s, %s)', groupName, newState);
  if(newState == 'on') {
    $('.light-' + groupName + ' i').removeClass('mdi-lightbulb-outline');
    $('.light-' + groupName + ' i').addClass('mdi-lightbulb-on');
  } else {
    $('.light-' + groupName + ' i').removeClass('mdi-lightbulb-on');
    $('.light-' + groupName + ' i').addClass('mdi-lightbulb-outline');
  }
}

/**
 * Handle the click of an alarm button.
 *
 * @param name [String] button name - "stay", "leave", "disarm", or "enterCode".
 */
export function handleAlarmButton(name) {
  if (name == 'stay') {
    console.log('Got "stay" alarm button.');
    sendEvent({ 'type': 'stay', 'client': myIP });
  } else if (name == 'leave') {
    console.log('Got "leave" alarm button.');
    sendEvent({ 'type': 'leave', 'client': myIP });
  } else if (name == 'disarm') {
    console.log('Got "disarm" alarm button.');
    sendEvent({ 'type': 'disarm', 'client': myIP });
  } else if (name == 'enterCode') {
    if (currentCode.trim() == "") {
      console.log('Not sending empty code.');
      return;
    }
    console.log('Sending Code: "%s"', currentCode);
    sendEvent({ 'type': 'enterCode', 'code': currentCode, 'client': myIP });
    clearTimeout(inputTimeout);
    currentCode = '';
  }
}
window.handleAlarmButton = handleAlarmButton;

/**
 * Handle click of the duress button.
 */
export function handleDuressButton() {
  console.log('Got "duress" alarm button.');
  if(inDuress) {
    sendEvent({'type': 'duress', 'client': myIP});
  } else {
    sendEvent({'type': 'end-duress', 'client': myIP});
  }
}
window.handleDuressButton = handleDuressButton;

/**
 * Handle the press of a button on the numeric pad for the alarm code. Appends
 * the character to the current code string, and sets a timeout after which we
 * should clear the current code string.
 *
 * @param char [String] the code character entered.
 */
export function handleCode(char) {
  console.log('Got alarm code entry: %s; currentCode=%s', char, currentCode);
  clearTimeout(inputTimeout);
  inputTimeout = setTimeout(function() { currentCode = ''; }, 5000);
  currentCode = currentCode + char;
}
window.handleCode = handleCode;

/**
 * Handle the click of a light-control button.
 *
 * @param name [String] light or group name - "porch", "lr" or "kitchen".
 */
export function handleLightButton(name) {
  console.log('Got light button: %s', name);
  if(groupStates[name] == 'on') {
    callService(hawsConn, 'homeassistant', 'turn_off', { 'entity_id': 'group.' + name });
  } else {
    callService(hawsConn, 'homeassistant', 'turn_on', { 'entity_id': 'group.' + name });
  }
}
window.handleLightButton = handleLightButton;

/**
 * Send a custom Event to HASS
 *
 * @param data [Object] data to send with the event
 */
function sendEvent(data) {
  console.log('Send Event: ' + JSON.stringify(data));
  $.ajax(
    {
      url: hassBaseUrl + '/api/events/CUSTOM-DOORPANELS',
      contentType: 'application/json',
      data: JSON.stringify(data),
      headers: {
        'Authorization': 'Bearer ' + apiToken
      },
      method: 'POST',
      success: function(result){ console.log('sendEvent response: ' + JSON.stringify(result)); },
      error: function(xhr, status, error) { console.log('sendEvent status=' + status + ' error: ' + error); }
    }
  );
}

/**
 * Update the display/UI depending on the current state of the alarm.
 *
 * @param st_name [String] the current state of the alarmstate input_select.
 */
function handleAlarmState(st_name) {
  if (st_name == 'Home') {
    $('#status').hide();
    $('#disarmed').hide();
    $('#away-armed').hide();
    $('#home-armed').show();
  } else if (st_name == 'Away') {
    $('#status').hide();
    $('#disarmed').hide();
    $('#home-armed').hide();
    $('#away-armed').show();
  } else if (st_name == 'Disarmed') {
    $('#status').hide();
    $('#home-armed').hide();
    $('#away-armed').hide();
    $('#disarmed').show();
  } else {
    $('#disarmed').hide();
    $('#home-armed').hide();
    $('#away-armed').hide();
    $('#status').show();
  }
}

/**
 * Update the display/UI depending on the current duress state.
 *
 * @param st_name [String] the current state of input_boolean.alarm_duress
 */
function handleAlarmDuress(st_name) {
  console.log("Handle change of Duress to: " + st_name);
  if (st_name == "on") {
    inDuress = true;
    $('.duress').addClass('duress-active');
  } else {
    inDuress = false;
    $('.duress').removeClass('duress-active');
  }
}

/**
 * Get Local IP Address
 *
 * From: <https://gist.github.com/hectorguo/672844c319547498dcb569df583f959d>
 *
 * @returns Promise Object
 *
 * getLocalIP().then((ipAddr) => {
 *    console.log(ipAddr); // 192.168.0.122
 * });
 */
function getLocalIP() {
  return new Promise(function(resolve, reject) {
    // NOTE: window.RTCPeerConnection is "not a constructor" in FF22/23
    var RTCPeerConnection = /*window.RTCPeerConnection ||*/ window.webkitRTCPeerConnection || window.mozRTCPeerConnection;

    if (!RTCPeerConnection) {
      reject('Your browser does not support this API');
    }

    var rtc = new RTCPeerConnection({iceServers:[]});
    var addrs = {};
    addrs["0.0.0.0"] = false;

    function grepSDP(sdp) {
        var hosts = [];
        var finalIP = '';
        sdp.split('\r\n').forEach(function (line) { // c.f. http://tools.ietf.org/html/rfc4566#page-39
            if (~line.indexOf("a=candidate")) {     // http://tools.ietf.org/html/rfc4566#section-5.13
                var parts = line.split(' '),        // http://tools.ietf.org/html/rfc5245#section-15.1
                    addr = parts[4],
                    type = parts[7];
                if (type === 'host') {
                    finalIP = addr;
                }
            } else if (~line.indexOf("c=")) {       // http://tools.ietf.org/html/rfc4566#section-5.7
                var parts = line.split(' '),
                    addr = parts[2];
                finalIP = addr;
            }
        });
        return finalIP;
    }

    if (1 || window.mozRTCPeerConnection) {      // FF [and now Chrome!] needs a channel/stream to proceed
        rtc.createDataChannel('', {reliable:false});
    };

    rtc.onicecandidate = function (evt) {
        // convert the candidate to SDP so we can run it through our general parser
        // see https://twitter.com/lancestout/status/525796175425720320 for details
        if (evt.candidate) {
          var addr = grepSDP("a="+evt.candidate.candidate);
          resolve(addr);
        }
    };
    rtc.createOffer(function (offerDesc) {
        rtc.setLocalDescription(offerDesc);
    }, function (e) { console.warn("offer failed", e); });
  });
}
