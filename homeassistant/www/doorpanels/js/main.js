var myIP = null;
var hawsConn = null;
var hassBaseUrl = null;
var currentCode = '';
var inputTimeout = null;
var groupStates = {};

/**
 * Main entrypoint / pre-initializer. Finds our IP address then calls
 * `doorPanelInit()`.
 */
function doorPanelPreInit() {
  hassBaseUrl = getHassWsUrl();
  $('#status').html('Connecting to ' + hassBaseUrl + ' ...');
  findIP(gotIp);
}

/**
 * Main initialization function, called after `gotIp()` found our IP address.
 */
function doorPanelInit() {
  $('#status').html('Connecting to ' + hassBaseUrl + ' ...<br />my IP: ' + myIP);
  HAWS.getAuth({ hassBaseUrl }).then (
    auth => {
      HAWS.createConnection(auth).then(
        conn => {
          hawsConn = conn;
          conn.subscribeEvents(handleEvent);
          conn.getStates().then(states => {
            states.forEach(function(s) {
              if (s.entity_id == 'input_select.alarmstate') { handleAlarmState(s.state); }
              if (s.entity_id.startsWith('group.')) {
                var groupName = s.entity_id.split(".")[1];
                groupStates[groupName] = s.state;
                handleLightStateChange(groupName, s.state);
              }
            });
          });
        },
        err => {
          $('#status').html('Connection to ' + hassBaseUrl + ' failed; retry in 10s.<br />my IP: ' + myIP);
          window.setTimeout(doorPanelInit, 10000);
        }
      )
    }
  );
}

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
function handleAlarmButton(name) {
  if (name == 'stay') {
    console.log('Got "stay" alarm button.');
    hawsConn.callService('CUSTOM', 'doorpanels', { 'type': 'stay', 'client': myIP });
  } else if (name == 'leave') {
    console.log('Got "leave" alarm button.');
    hawsConn.callService('CUSTOM', 'doorpanels', { 'type': 'leave', 'client': myIP });
  } else if (name == 'disarm') {
    console.log('Got "disarm" alarm button.');
    hawsConn.callService('CUSTOM', 'doorpanels', { 'type': 'disarm', 'client': myIP });
  } else if (name == 'enterCode') {
    if (currentCode.trim() == "") {
      console.log('Not sending empty code.');
      return;
    }
    console.log('Sending Code: "%s"', currentCode);
    hawsConn.callService('CUSTOM', 'doorpanels', { 'type': 'enterCode', 'code': currentCode, 'client': myIP });
    clearTimeout(inputTimeout);
    currentCode = '';
  }
}

/**
 * Handle the press of a button on the numeric pad for the alarm code. Appends
 * the character to the current code string, and sets a timeout after which we
 * should clear the current code string.
 *
 * @param char [String] the code character entered.
 */
function handleCode(char) {
  console.log('Got alarm code entry: %s; currentCode=%s', char, currentCode);
  clearTimeout(inputTimeout);
  inputTimeout = setTimeout(function() { currentCode = ''; }, 5000);
  currentCode = currentCode + char;
}

/**
 * Handle the click of a light-control button.
 *
 * @param name [String] light or group name - "porch", "lr" or "kitchen".
 */
function handleLightButton(name) {
  console.log('Got light button: %s', name);
  if(groupStates[name] == 'on') {
    hawsConn.callService('homeassistant', 'turn_off', { 'entity_id': 'group.' + name });
  } else {
    hawsConn.callService('homeassistant', 'turn_on', { 'entity_id': 'group.' + name });
  }
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
 * Using the current URL, find the URL for the HASS WebSocket API.
 */
function getHassWsUrl() {
  return 'ws://' + window.location.hostname + ':' + window.location.port + '/api/websocket';
}

/**
 * Callback for `findIP()` when this host's IP is found.
 */
function gotIp(ip) {
  if (myIP != null) { return null; }
  myIP = ip;
  doorPanelInit();
}

/**
 * Finds the local machine's IP address. We send this in the Event that
 * goes to HASS and is processed by AppDaemon.
 *
 * Source: https://stackoverflow.com/a/32841164/211734
 */
function findIP(callback) {
  var myPeerConnection = window.RTCPeerConnection || window.mozRTCPeerConnection || window.webkitRTCPeerConnection; //compatibility for firefox and chrome
  var pc = new myPeerConnection({iceServers: []}),
    noop = function() {},
    localIPs = {},
    ipRegex = /([0-9]{1,3}(\.[0-9]{1,3}){3}|[a-f0-9]{1,4}(:[a-f0-9]{1,4}){7})/g,
    key;

  function ipIterate(ip) {
    if (!localIPs[ip]) callback(ip);
    localIPs[ip] = true;
    // ok, don't get any more...
    ipIterate = noop;
  }
  pc.createDataChannel(""); //create a bogus data channel
  pc.createOffer(function(sdp) {
    sdp.sdp.split('\n').forEach(function(line) {
      if (line.indexOf('candidate') < 0) return;
      line.match(ipRegex).forEach(ipIterate);
    });
    pc.setLocalDescription(sdp, noop, noop);
  }, noop); // create offer and set local description
  pc.onicecandidate = function(ice) { //listen for candidate events
    if (!ice || !ice.candidate || !ice.candidate.candidate || !ice.candidate.candidate.match(ipRegex)) return;
    ice.candidate.candidate.match(ipRegex).forEach(ipIterate);
  };
}
