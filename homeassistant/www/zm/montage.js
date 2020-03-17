function getDimensions(url) {
  dims = {};
  $.get({
    url: url,
    success: function(data) {
      for (mon of data['monitors']) {
        m = mon['Monitor'];
        dims[parseInt(m['Id'])] = [parseInt(m['Width']), parseInt(m['Height'])];
      }
    },
    async: false
  });
  return dims
}

function fit_dimensions(orig_w, orig_h, box_w, box_h) {
  if (orig_w > box_w) {
    wscale = box_w / orig_w;
    hscale = box_h / orig_h;
  } else {
    wscale = orig_w / box_w;
    hscale = orig_h / box_h;
  }
  if (wscale < hscale) {
    scale = wscale;
  } else {
    scale = hscale;
  }
  return [Math.floor(orig_w * scale), Math.floor(orig_h * scale)]
}

function imageDiv(host, mon_id, fitWidth, fitHeight, orig_dims) {
  new_dims = fit_dimensions(orig_dims[0], orig_dims[1], fitWidth, fitHeight);
  iWidth = new_dims[0] - 8;
  rHeight = new_dims[1];
  if (host == "guarddog") {
    link = "http://guarddog/zm/index.php?view=watch&mid=" + mon_id;
    url = "http://guarddog/zm/cgi-bin/nph-zms?mode=jpeg&maxfps=5&monitor=" + mon_id;
  } else if (host == "telescreen") {
    link = "http://telescreen/zm/index.php?view=watch&mid=" + mon_id;
    url = "http://telescreen/zm/cgi-bin/nph-zms?mode=jpeg&maxfps=5&monitor=" + mon_id;
  } else {
    alert("Unsupported host: " + host);
    return "";
  }
  s = '  <div style="float: left;">\n';
  s = s + '    <a href="' + link + '" target="_blank"><img src="' + url + '&width=' + iWidth + 'px&height=' + rHeight + 'px" width="' + iWidth + '" height="' + rHeight + '"></a>\n';
  s = s + '  </div>\n';
  return s;
}

function showMonitors(monitors) {
  dimensions = {
    "guarddog": getDimensions("http://guarddog/zm/api/monitors.json"),
    "telescreen": getDimensions("http://telescreen/zm/api/monitors.json")
  }
  // console.log(dimensions);
  availHeight = window.innerHeight;
  availHeight = Math.floor(availHeight - (availHeight * 0.05));
  width = window.innerWidth;
  numRows = monitors.length;
  rowHeight = Math.floor(availHeight / numRows);
  content = "";
  for (row of monitors) {
    content = content + '<div class="clearfix">\n';
    numImages = row.length;
    imgWidth = Math.floor(width / numImages);
    for (img of row) {
      content += imageDiv(img[0], img[1], imgWidth, rowHeight, dimensions[img[0]][img[1]]);
    }
    content = content + '</div>\n';
  }
  document.getElementById("container").innerHTML = content;
}
