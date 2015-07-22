#!/usr/bin/env python

import cgi
import string

print "Content-Type: text/html"
print ""

exit()

page_str = """
<!DOCTYPE html>
<meta charset="utf-8">
<style>

  html, body, svg {
    margin: 0;
    padding: 0;
  }

  .legend {                                                   
    font-size: 10px;                                         
  }
  rect {
    stroke-width: 2;
  }

  .node circle {
    stroke: white;
    stroke-width: 2px;
    opacity: 1.0;
  }

  line {
    stroke-width: 4px;
    stroke-opacity: 1.0;
    //stroke: "black"; 
  }

  body {
    /* Scaling for different browsers */
    -ms-transform: scale(1,1);
    -webkit-transform: scale(1,1);
    transform: scale(1,1);
  }

  .legend {
    position: absolute;
    bottom: 0px;
    right: 0px;
  }

</style>
<body>
  <form>
    <input type="hidden" id="fid" name="fid" value="$file_id" />
  </form>
  <object data="legend.svg" type="image/svg+xml" width="400px" height="300px" class="legend"></object>
  <script type="text/javascript" src="../bower_components/d3/d3.min.js"></script> 
  <script type="text/javascript" src="../bower_components/papaparse/papaparse.min.js"></script>
  <script type="text/javascript" src="../bower_components/jquery/dist/jquery.min.js"></script> 
  <script type="text/javascript" src="../bower_components/tipsy/src/javascripts/jquery.tipsy.js"></script> 
  <link href="tipsy_style.css" rel="stylesheet" type="text/css" />
  <script type="text/javascript" src="networkview.js"></script>
</body>
"""

form = cgi.FieldStorage()
if "fid" in form:
    file_id = form["fid"].value
else:
    file_id = ""
out = string.Template(page_str).substitute(file_id=file_id)
print out
