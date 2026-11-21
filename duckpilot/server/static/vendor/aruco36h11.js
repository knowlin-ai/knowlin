// js-aruco2 2.0.0 (MIT, Juan Mellado / Damiano Falcioni) mit dem Wörterbuch AprilTag 36h11 (BSD-2-Clause,
// The Regents of the University of Michigan) – für Knowlin als ES-Modul gebündelt (seit 0.49: Duck Cards lesen).
// Lizenzen: vendor/ARUCO-LICENSE.txt. Geändert nur: allein das Wörterbuch tag36h11, kein require().
const scope = {};
(function () {
/*
Copyright (c) 2011 Juan Mellado

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
*/

/*
References:
- "OpenCV: Open Computer Vision Library"
  http://sourceforge.net/projects/opencvlibrary/
- "Stack Blur: Fast But Goodlooking"
  http://incubator.quasimondo.com/processing/fast_blur_deluxe.php
*/

var CV = CV || {};
this.CV = CV;

CV.Image = function(width, height, data){
  this.width = width || 0;
  this.height = height || 0;
  this.data = data || [];
};

CV.grayscale = function(imageSrc, imageDst){
  var src = imageSrc.data, dst = imageDst.data, len = src.length,
      i = 0, j = 0;

  for (; i < len; i += 4){
    dst[j ++] =
      (src[i] * 0.299 + src[i + 1] * 0.587 + src[i + 2] * 0.114 + 0.5) & 0xff;
  }

  imageDst.width = imageSrc.width;
  imageDst.height = imageSrc.height;

  return imageDst;
};

CV.threshold = function(imageSrc, imageDst, threshold){
  var src = imageSrc.data, dst = imageDst.data,
      len = src.length, tab = [], i;

  for (i = 0; i < 256; ++ i){
    tab[i] = i <= threshold? 0: 255;
  }

  for (i = 0; i < len; ++ i){
    dst[i] = tab[ src[i] ];
  }

  imageDst.width = imageSrc.width;
  imageDst.height = imageSrc.height;

  return imageDst;
};

CV.adaptiveThreshold = function(imageSrc, imageDst, kernelSize, threshold){
  var src = imageSrc.data, dst = imageDst.data, len = src.length, tab = [], i;

  CV.stackBoxBlur(imageSrc, imageDst, kernelSize);

  for (i = 0; i < 768; ++ i){
    tab[i] = (i - 255 <= -threshold)? 255: 0;
  }

  for (i = 0; i < len; ++ i){
    dst[i] = tab[ src[i] - dst[i] + 255 ];
  }

  imageDst.width = imageSrc.width;
  imageDst.height = imageSrc.height;

  return imageDst;
};

CV.otsu = function(imageSrc){
  var src = imageSrc.data, len = src.length, hist = [],
      threshold = 0, sum = 0, sumB = 0, wB = 0, wF = 0, max = 0,
      mu, between, i;

  for (i = 0; i < 256; ++ i){
    hist[i] = 0;
  }

  for (i = 0; i < len; ++ i){
    hist[ src[i] ] ++;
  }

  for (i = 0; i < 256; ++ i){
    sum += hist[i] * i;
  }

  for (i = 0; i < 256; ++ i){
    wB += hist[i];
    if (0 !== wB){

      wF = len - wB;
      if (0 === wF){
        break;
      }

      sumB += hist[i] * i;

      mu = (sumB / wB) - ( (sum - sumB) / wF );

      between = wB * wF * mu * mu;

      if (between > max){
        max = between;
        threshold = i;
      }
    }
  }

  return threshold;
};

CV.stackBoxBlurMult =
  [1, 171, 205, 293, 57, 373, 79, 137, 241, 27, 391, 357, 41, 19, 283, 265];

CV.stackBoxBlurShift =
  [0, 9, 10, 11, 9, 12, 10, 11, 12, 9, 13, 13, 10, 9, 13, 13];

CV.BlurStack = function(){
  this.color = 0;
  this.next = null;
};

CV.stackBoxBlur = function(imageSrc, imageDst, kernelSize){
  var src = imageSrc.data, dst = imageDst.data,
      height = imageSrc.height, width = imageSrc.width,
      heightMinus1 = height - 1, widthMinus1 = width - 1,
      size = kernelSize + kernelSize + 1, radius = kernelSize + 1,
      mult = CV.stackBoxBlurMult[kernelSize],
      shift = CV.stackBoxBlurShift[kernelSize],
      stack, stackStart, color, sum, pos, start, p, x, y, i;

  stack = stackStart = new CV.BlurStack();
  for (i = 1; i < size; ++ i){
    stack = stack.next = new CV.BlurStack();
  }
  stack.next = stackStart;

  pos = 0;

  for (y = 0; y < height; ++ y){
    start = pos;

    color = src[pos];
    sum = radius * color;

    stack = stackStart;
    for (i = 0; i < radius; ++ i){
      stack.color = color;
      stack = stack.next;
    }
    for (i = 1; i < radius; ++ i){
      stack.color = src[pos + i];
      sum += stack.color;
      stack = stack.next;
    }

    stack = stackStart;
    for (x = 0; x < width; ++ x){
      dst[pos ++] = (sum * mult) >>> shift;

      p = x + radius;
      p = start + (p < widthMinus1? p: widthMinus1);
      sum -= stack.color - src[p];

      stack.color = src[p];
      stack = stack.next;
    }
  }

  for (x = 0; x < width; ++ x){
    pos = x;
    start = pos + width;

    color = dst[pos];
    sum = radius * color;

    stack = stackStart;
    for (i = 0; i < radius; ++ i){
      stack.color = color;
      stack = stack.next;
    }
    for (i = 1; i < radius; ++ i){
      stack.color = dst[start];
      sum += stack.color;
      stack = stack.next;

      start += width;
    }

    stack = stackStart;
    for (y = 0; y < height; ++ y){
      dst[pos] = (sum * mult) >>> shift;

      p = y + radius;
      p = x + ( (p < heightMinus1? p: heightMinus1) * width );
      sum -= stack.color - dst[p];

      stack.color = dst[p];
      stack = stack.next;

      pos += width;
    }
  }

  return imageDst;
};

CV.gaussianBlur = function(imageSrc, imageDst, imageMean, kernelSize){
  var kernel = CV.gaussianKernel(kernelSize);

  imageDst.width = imageSrc.width;
  imageDst.height = imageSrc.height;

  imageMean.width = imageSrc.width;
  imageMean.height = imageSrc.height;

  CV.gaussianBlurFilter(imageSrc, imageMean, kernel, true);
  CV.gaussianBlurFilter(imageMean, imageDst, kernel, false);

  return imageDst;
};

CV.gaussianBlurFilter = function(imageSrc, imageDst, kernel, horizontal){
  var src = imageSrc.data, dst = imageDst.data,
      height = imageSrc.height, width = imageSrc.width,
      pos = 0, limit = kernel.length >> 1,
      cur, value, i, j, k;

  for (i = 0; i < height; ++ i){

    for (j = 0; j < width; ++ j){
      value = 0.0;

      for (k = -limit; k <= limit; ++ k){

        if (horizontal){
          cur = pos + k;
          if (j + k < 0){
            cur = pos;
          }
          else if (j + k >= width){
            cur = pos;
          }
        }else{
          cur = pos + (k * width);
          if (i + k < 0){
            cur = pos;
          }
          else if (i + k >= height){
            cur = pos;
          }
        }

        value += kernel[limit + k] * src[cur];
      }

      dst[pos ++] = horizontal? value: (value + 0.5) & 0xff;
    }
  }

  return imageDst;
};

CV.gaussianKernel = function(kernelSize){
  var tab =
    [ [1],
      [0.25, 0.5, 0.25],
      [0.0625, 0.25, 0.375, 0.25, 0.0625],
      [0.03125, 0.109375, 0.21875, 0.28125, 0.21875, 0.109375, 0.03125] ],
    kernel = [], center, sigma, scale2X, sum, x, i;

  if ( (kernelSize <= 7) && (kernelSize % 2 === 1) ){
    kernel = tab[kernelSize >> 1];
  }else{
    center = (kernelSize - 1.0) * 0.5;
    sigma = 0.8 + (0.3 * (center - 1.0) );
    scale2X = -0.5 / (sigma * sigma);
    sum = 0.0;
    for (i = 0; i < kernelSize; ++ i){
      x = i - center;
      sum += kernel[i] = Math.exp(scale2X * x * x);
    }
    sum = 1 / sum;
    for (i = 0; i < kernelSize; ++ i){
      kernel[i] *= sum;
    }
  }

  return kernel;
};

CV.findContours = function(imageSrc, binary){
  var width = imageSrc.width, height = imageSrc.height, contours = [],
      src, deltas, pos, pix, nbd, outer, hole, i, j;

  src = CV.binaryBorder(imageSrc, binary);

  deltas = CV.neighborhoodDeltas(width + 2);

  pos = width + 3;
  nbd = 1;

  for (i = 0; i < height; ++ i, pos += 2){

    for (j = 0; j < width; ++ j, ++ pos){
      pix = src[pos];

      if (0 !== pix){
        outer = hole = false;

        if (1 === pix && 0 === src[pos - 1]){
          outer = true;
        }
        else if (pix >= 1 && 0 === src[pos + 1]){
          hole = true;
        }

        if (outer || hole){
          ++ nbd;

          contours.push( CV.borderFollowing(src, pos, nbd, {x: j, y: i}, hole, deltas) );
        }
      }
    }
  }

  return contours;
};

CV.borderFollowing = function(src, pos, nbd, point, hole, deltas){
  var contour = [], pos1, pos3, pos4, s, s_end, s_prev;

  contour.hole = hole;

  s = s_end = hole? 0: 4;
  do{
    s = (s - 1) & 7;
    pos1 = pos + deltas[s];
    if (src[pos1] !== 0){
      break;
    }
  }while(s !== s_end);

  if (s === s_end){
    src[pos] = -nbd;
    contour.push( {x: point.x, y: point.y} );

  }else{
    pos3 = pos;
    s_prev = s ^ 4;

    while(true){
      s_end = s;

      do{
        pos4 = pos3 + deltas[++ s];
      }while(src[pos4] === 0);

      s &= 7;

      if ( ( (s - 1) >>> 0) < (s_end >>> 0) ){
        src[pos3] = -nbd;
      }
      else if (src[pos3] === 1){
        src[pos3] = nbd;
      }

      contour.push( {x: point.x, y: point.y} );

      s_prev = s;

      point.x += CV.neighborhood[s][0];
      point.y += CV.neighborhood[s][1];

      if ( (pos4 === pos) && (pos3 === pos1) ){
        break;
      }

      pos3 = pos4;
      s = (s + 4) & 7;
    }
  }

  return contour;
};

CV.neighborhood =
  [ [1, 0], [1, -1], [0, -1], [-1, -1], [-1, 0], [-1, 1], [0, 1], [1, 1] ];

CV.neighborhoodDeltas = function(width){
  var deltas = [], len = CV.neighborhood.length, i = 0;

  for (; i < len; ++ i){
    deltas[i] = CV.neighborhood[i][0] + (CV.neighborhood[i][1] * width);
  }

  return deltas.concat(deltas);
};

CV.approxPolyDP = function(contour, epsilon){
  var slice = {start_index: 0, end_index: 0},
      right_slice = {start_index: 0, end_index: 0},
      poly = [], stack = [], len = contour.length,
      pt, start_pt, end_pt, dist, max_dist, le_eps,
      dx, dy, i, j, k;

  epsilon *= epsilon;

  k = 0;

  for (i = 0; i < 3; ++ i){
    max_dist = 0;

    k = (k + right_slice.start_index) % len;
    start_pt = contour[k];
    if (++ k === len) {k = 0;}

    for (j = 1; j < len; ++ j){
      pt = contour[k];
      if (++ k === len) {k = 0;}

      dx = pt.x - start_pt.x;
      dy = pt.y - start_pt.y;
      dist = dx * dx + dy * dy;

      if (dist > max_dist){
        max_dist = dist;
        right_slice.start_index = j;
      }
    }
  }

  if (max_dist <= epsilon){
    poly.push( {x: start_pt.x, y: start_pt.y} );

  }else{
    slice.start_index = k;
    slice.end_index = (right_slice.start_index += slice.start_index);

    right_slice.start_index -= right_slice.start_index >= len? len: 0;
    right_slice.end_index = slice.start_index;
    if (right_slice.end_index < right_slice.start_index){
      right_slice.end_index += len;
    }

    stack.push( {start_index: right_slice.start_index, end_index: right_slice.end_index} );
    stack.push( {start_index: slice.start_index, end_index: slice.end_index} );
  }

  while(stack.length !== 0){
    slice = stack.pop();

    end_pt = contour[slice.end_index % len];
    start_pt = contour[k = slice.start_index % len];
    if (++ k === len) {k = 0;}

    if (slice.end_index <= slice.start_index + 1){
      le_eps = true;

    }else{
      max_dist = 0;

      dx = end_pt.x - start_pt.x;
      dy = end_pt.y - start_pt.y;

      for (i = slice.start_index + 1; i < slice.end_index; ++ i){
        pt = contour[k];
        if (++ k === len) {k = 0;}

        dist = Math.abs( (pt.y - start_pt.y) * dx - (pt.x - start_pt.x) * dy);

        if (dist > max_dist){
          max_dist = dist;
          right_slice.start_index = i;
        }
      }

      le_eps = max_dist * max_dist <= epsilon * (dx * dx + dy * dy);
    }

    if (le_eps){
      poly.push( {x: start_pt.x, y: start_pt.y} );

    }else{
      right_slice.end_index = slice.end_index;
      slice.end_index = right_slice.start_index;

      stack.push( {start_index: right_slice.start_index, end_index: right_slice.end_index} );
      stack.push( {start_index: slice.start_index, end_index: slice.end_index} );
    }
  }

  return poly;
};

CV.warp = function(imageSrc, imageDst, contour, warpSize){
  var src = imageSrc.data, dst = imageDst.data,
      width = imageSrc.width, height = imageSrc.height,
      pos = 0,
      sx1, sx2, dx1, dx2, sy1, sy2, dy1, dy2, p1, p2, p3, p4,
      m, r, s, t, u, v, w, x, y, i, j;

  m = CV.getPerspectiveTransform(contour, warpSize - 1);

  r = m[8];
  s = m[2];
  t = m[5];

  for (i = 0; i < warpSize; ++ i){
    r += m[7];
    s += m[1];
    t += m[4];

    u = r;
    v = s;
    w = t;

    for (j = 0; j < warpSize; ++ j){
      u += m[6];
      v += m[0];
      w += m[3];

      x = v / u;
      y = w / u;

      sx1 = x >>> 0;
      sx2 = (sx1 === width - 1)? sx1: sx1 + 1;
      dx1 = x - sx1;
      dx2 = 1.0 - dx1;

      sy1 = y >>> 0;
      sy2 = (sy1 === height - 1)? sy1: sy1 + 1;
      dy1 = y - sy1;
      dy2 = 1.0 - dy1;

      p1 = p2 = sy1 * width;
      p3 = p4 = sy2 * width;

      dst[pos ++] =
        (dy2 * (dx2 * src[p1 + sx1] + dx1 * src[p2 + sx2]) +
         dy1 * (dx2 * src[p3 + sx1] + dx1 * src[p4 + sx2]) ) & 0xff;

    }
  }

  imageDst.width = warpSize;
  imageDst.height = warpSize;

  return imageDst;
};

CV.getPerspectiveTransform = function(src, size){
  var rq = CV.square2quad(src);

  rq[0] /= size;
  rq[1] /= size;
  rq[3] /= size;
  rq[4] /= size;
  rq[6] /= size;
  rq[7] /= size;

  return rq;
};

CV.square2quad = function(src){
  var sq = [], px, py, dx1, dx2, dy1, dy2, den;

  px = src[0].x - src[1].x + src[2].x - src[3].x;
  py = src[0].y - src[1].y + src[2].y - src[3].y;

  if (0 === px && 0 === py){
    sq[0] = src[1].x - src[0].x;
    sq[1] = src[2].x - src[1].x;
    sq[2] = src[0].x;
    sq[3] = src[1].y - src[0].y;
    sq[4] = src[2].y - src[1].y;
    sq[5] = src[0].y;
    sq[6] = 0;
    sq[7] = 0;
    sq[8] = 1;

  }else{
    dx1 = src[1].x - src[2].x;
    dx2 = src[3].x - src[2].x;
    dy1 = src[1].y - src[2].y;
    dy2 = src[3].y - src[2].y;
    den = dx1 * dy2 - dx2 * dy1;

    sq[6] = (px * dy2 - dx2 * py) / den;
    sq[7] = (dx1 * py - px * dy1) / den;
    sq[8] = 1;
    sq[0] = src[1].x - src[0].x + sq[6] * src[1].x;
    sq[1] = src[3].x - src[0].x + sq[7] * src[3].x;
    sq[2] = src[0].x;
    sq[3] = src[1].y - src[0].y + sq[6] * src[1].y;
    sq[4] = src[3].y - src[0].y + sq[7] * src[3].y;
    sq[5] = src[0].y;
  }

  return sq;
};

CV.isContourConvex = function(contour){
  var orientation = 0, convex = true,
      len = contour.length, i = 0, j = 0,
      cur_pt, prev_pt, dxdy0, dydx0, dx0, dy0, dx, dy;

  prev_pt = contour[len - 1];
  cur_pt = contour[0];

  dx0 = cur_pt.x - prev_pt.x;
  dy0 = cur_pt.y - prev_pt.y;

  for (; i < len; ++ i){
    if (++ j === len) {j = 0;}

    prev_pt = cur_pt;
    cur_pt = contour[j];

    dx = cur_pt.x - prev_pt.x;
    dy = cur_pt.y - prev_pt.y;
    dxdy0 = dx * dy0;
    dydx0 = dy * dx0;

    orientation |= dydx0 > dxdy0? 1: (dydx0 < dxdy0? 2: 3);

    if (3 === orientation){
        convex = false;
        break;
    }

    dx0 = dx;
    dy0 = dy;
  }

  return convex;
};

CV.perimeter = function(poly){
  var len = poly.length, i = 0, j = len - 1,
      p = 0.0, dx, dy;

  for (; i < len; j = i ++){
    dx = poly[i].x - poly[j].x;
    dy = poly[i].y - poly[j].y;

    p += Math.sqrt(dx * dx + dy * dy) ;
  }

  return p;
};

CV.minEdgeLength = function(poly){
  var len = poly.length, i = 0, j = len - 1,
      min = Infinity, d, dx, dy;

  for (; i < len; j = i ++){
    dx = poly[i].x - poly[j].x;
    dy = poly[i].y - poly[j].y;

    d = dx * dx + dy * dy;

    if (d < min){
      min = d;
    }
  }

  return Math.sqrt(min);
};

CV.countNonZero = function(imageSrc, square){
  var src = imageSrc.data, height = square.height, width = square.width,
      pos = square.x + (square.y * imageSrc.width),
      span = imageSrc.width - width,
      nz = 0, i, j;

  for (i = 0; i < height; ++ i){

    for (j = 0; j < width; ++ j){

      if ( 0 !== src[pos ++] ){
        ++ nz;
      }
    }

    pos += span;
  }

  return nz;
};

CV.binaryBorder = function(imageSrc, dst){
  var src = imageSrc.data, height = imageSrc.height, width = imageSrc.width,
      posSrc = 0, posDst = 0, i, j;

  for (j = -2; j < width; ++ j){
    dst[posDst ++] = 0;
  }

  for (i = 0; i < height; ++ i){
    dst[posDst ++] = 0;

    for (j = 0; j < width; ++ j){
      dst[posDst ++] = (0 === src[posSrc ++]? 0: 1);
    }

    dst[posDst ++] = 0;
  }

  for (j = -2; j < width; ++ j){
    dst[posDst ++] = 0;
  }

  return dst;
};

}).call(scope);
(function () {
/*
Copyright (c) 2020 Damiano Falcioni
Copyright (c) 2011 Juan Mellado

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
*/

/*
References:
- "ArUco: a minimal library for Augmented Reality applications based on OpenCv"
  http://www.uco.es/investiga/grupos/ava/node/26
- "js-aruco: a port to JavaScript of the ArUco library"
  https://github.com/jcmellado/js-aruco
*/

var AR = {};
var CV = this.CV;
this.AR = AR;

AR.DICTIONARIES = {};

AR.Dictionary = function (dicName) {
  this.codes = {};
  this.codeList = [];
  this.tau = 0;
  this._initialize(dicName);
};

AR.Dictionary.prototype._initialize = function (dicName) {
  this.codes = {};
  this.codeList = [];
  this.tau = 0;
  this.nBits = 0;
  this.markSize = 0;
  this.dicName = dicName;
  var dictionary = AR.DICTIONARIES[dicName];
  if (!dictionary)
    throw 'The dictionary "' + dicName + '" is not recognized.';
  
  this.nBits = dictionary.nBits;
  this.markSize = Math.sqrt(dictionary.nBits) + 2;
  for (var i = 0; i < dictionary.codeList.length; i++) {
    var code = null;
    if (typeof dictionary.codeList[i] === 'number')
      code = this._hex2bin(dictionary.codeList[i], dictionary.nBits);
    if (typeof dictionary.codeList[i] === 'string')
      code = this._hex2bin(parseInt(dictionary.codeList[i], 16), dictionary.nBits);
    if (Array.isArray(dictionary.codeList[i])) 
      code = this._bytes2bin(dictionary.codeList[i], dictionary.nBits);
    if (code === null) 
      throw 'Invalid code ' + i + ' in dictionary ' + dicName + ': ' + JSON.stringify(dictionary.codeList[i]);
    if (code.length != dictionary.nBits)
      throw 'The code ' + i + ' in dictionary ' + dicName + ' is not ' +  dictionary.nBits + ' bits long but ' + code.length + ': ' + code;
    this.codeList.push(code);
    this.codes[code] = {
      id: i
    };
  }
  this.tau = dictionary.tau || this._calculateTau();
};

AR.Dictionary.prototype.find = function (bits) {
  var val = '',
    i, j;
  for (i = 0; i < bits.length; i++) {
    var bitRow = bits[i];
    for (j = 0; j < bitRow.length; j++) {
      val += bitRow[j];
    }
  }
  var minFound = this.codes[val];
  if (minFound)
    return {
      id: minFound.id,
      distance: 0
    };

  for (i = 0; i < this.codeList.length; i++) {
    var code = this.codeList[i];
    var distance = this._hammingDistance(val, code);
    if (this._hammingDistance(val, code) < this.tau) {
      if (!minFound || minFound.distance > distance) {
        minFound = {
          id: this.codes[code].id,
          distance: distance
        };
      }
    }
  }
  return minFound;
};

AR.Dictionary.prototype._hex2bin = function (hex, nBits) {
  return hex.toString(2).padStart(nBits, '0');
};

AR.Dictionary.prototype._bytes2bin = function (byteList, nBits) {
  var bits = '', byte;
  for (byte of byteList) {
    bits += byte.toString(2).padStart(bits.length + 8 > nBits?nBits - bits.length:8, '0');
  }
  return bits;
};

AR.Dictionary.prototype._hammingDistance = function (str1, str2) {
  if (str1.length != str2.length)
    throw 'Hamming distance calculation require inputs of the same length';
  var distance = 0,
    i;
  for (i = 0; i < str1.length; i++)
    if (str1[i] !== str2[i])
      distance += 1;
  return distance;
};

AR.Dictionary.prototype._calculateTau = function () {
  var tau = Number.MAX_VALUE;
  for(var i=0;i<this.codeList.length;i++)
    for(var j=i+1;j<this.codeList.length;j++) {
      var distance = this._hammingDistance(this.codeList[i], this.codeList[j]);
      tau = distance < tau ? distance : tau;
    }
  return tau;
};

AR.Dictionary.prototype.generateSVG = function (id) {
  var code = this.codeList[id];
  if (code == null)
    throw 'The id "' + id + '" is not valid for the dictionary "' + this.dicName + '". ID must be between 0 and ' + (this.codeList.length-1) + ' included.';
  var size = this.markSize - 2;
  var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '+ (size+4) + ' ' + (size+4) + '">';
  svg += '<rect x="0" y="0" width="' + (size+4) + '" height="' + (size+4) + '" fill="white"/>';
  svg += '<rect x="1" y="1" width="' + (size+2) + '" height="' + (size+2) + '" fill="black"/>';
  for(var y=0;y<size;y++) {
    for(var x=0;x<size;x++) {
      if (code[y*size+x]=='1') 
        svg += '<rect x="' + (x+2) + '" y="' + (y+2) + '" width="1" height="1" fill="white"/>';
    }
  }
  svg += '</svg>';
  return svg;
};

AR.Marker = function (id, corners, hammingDistance) {
  this.id = id;
  this.corners = corners;
  this.hammingDistance = hammingDistance;
};

AR.Detector = function (config) {
  config = config || {};
  this.grey = new CV.Image();
  this.thres = new CV.Image();
  this.homography = new CV.Image();
  this.binary = [];
  this.contours = [];
  this.polys = [];
  this.candidates = [];
  config.dictionaryName = config.dictionaryName || 'ARUCO_MIP_36h12';
  this.dictionary = new AR.Dictionary(config.dictionaryName);
  this.dictionary.tau = config.maxHammingDistance != null ? config.maxHammingDistance : this.dictionary.tau;
};

AR.Detector.prototype.detectImage = function (width, height, data) {
  return this.detect({
    width: width,
    height: height,
    data: data
  });
};

AR.Detector.prototype.detectStreamInit = function (width, height, callback) {
  this.streamConfig = {};
  this.streamConfig.width = width;
  this.streamConfig.height = height;
  this.streamConfig.imageSize = width * height * 4; //provided image must be a sequence of rgba bytes (4 bytes represent a pixel)
  this.streamConfig.index = 0;
  this.streamConfig.imageData = new Uint8ClampedArray(this.streamConfig.imageSize);
  this.streamConfig.callback = callback || function (image, markerList) {};
};

//accept data chunks of different sizes
AR.Detector.prototype.detectStream = function (data) {
  for (var i = 0; i < data.length; i++) {
    this.streamConfig.imageData[this.streamConfig.index] = data[i];
    this.streamConfig.index = (this.streamConfig.index + 1) % this.streamConfig.imageSize;
    if (this.streamConfig.index == 0) {
      var image = {
        width: this.streamConfig.width,
        height: this.streamConfig.height,
        data: this.streamConfig.imageData
      };
      var markerList = this.detect(image);
      this.streamConfig.callback(image, markerList);
    }
  }
};

AR.Detector.prototype.detectMJPEGStreamInit = function (width, height, callback, decoderFn) {
  this.mjpeg = {
    decoderFn: decoderFn,
    chunks: [],
    SOI: [0xff, 0xd8],
    EOI: [0xff, 0xd9]
  };
  this.detectStreamInit(width, height, callback);
};

AR.Detector.prototype.detectMJPEGStream = function (chunk) {
  var eoiPos = chunk.findIndex(function (element, index, array) {
    return this.mjpeg.EOI[0] == element && array.length > index + 1 && this.mjpeg.EOI[1] == array[index + 1];
  });
  var soiPos = chunk.findIndex(function (element, index, array) {
    return this.mjpeg.SOI[0] == element && array.length > index + 1 && this.mjpeg.SOI[1] == array[index + 1];
  });

  if (eoiPos === -1) {
    this.mjpeg.chunks.push(chunk);
  } else {
    var part1 = chunk.slice(0, eoiPos + 2);
    if (part1.length) {
      this.mjpeg.chunks.push(part1);
    }
    if (this.mjpeg.chunks.length) {
      var jpegImage = this.mjpeg.chunks.flat();
      var rgba = this.mjpeg.decoderFn(jpegImage);
      this.detectStream(rgba);
    }
    this.mjpeg.chunks = [];
  }
  if (soiPos > -1) {
    this.mjpeg.chunks = [];
    this.mjpeg.chunks.push(chunk.slice(soiPos));
  }
};

AR.Detector.prototype.detect = function (image) {
  CV.grayscale(image, this.grey);
  CV.adaptiveThreshold(this.grey, this.thres, 2, 7);

  this.contours = CV.findContours(this.thres, this.binary);
  //Scale Fix: https://stackoverflow.com/questions/35936397/marker-detection-on-paper-sheet-using-javascript
  //this.candidates = this.findCandidates(this.contours, image.width * 0.20, 0.05, 10);
  this.candidates = this.findCandidates(this.contours, image.width * 0.01, 0.05, 10);
  this.candidates = this.clockwiseCorners(this.candidates);
  this.candidates = this.notTooNear(this.candidates, 10);

  return this.findMarkers(this.grey, this.candidates, 49);
};

AR.Detector.prototype.findCandidates = function (contours, minSize, epsilon, minLength) {
  var candidates = [],
    len = contours.length,
    contour, poly, i;

  this.polys = [];

  for (i = 0; i < len; ++i) {
    contour = contours[i];

    if (contour.length >= minSize) {
      poly = CV.approxPolyDP(contour, contour.length * epsilon);

      this.polys.push(poly);

      if ((4 === poly.length) && (CV.isContourConvex(poly))) {

        if (CV.minEdgeLength(poly) >= minLength) {
          candidates.push(poly);
        }
      }
    }
  }

  return candidates;
};

AR.Detector.prototype.clockwiseCorners = function (candidates) {
  var len = candidates.length,
    dx1, dx2, dy1, dy2, swap, i;

  for (i = 0; i < len; ++i) {
    dx1 = candidates[i][1].x - candidates[i][0].x;
    dy1 = candidates[i][1].y - candidates[i][0].y;
    dx2 = candidates[i][2].x - candidates[i][0].x;
    dy2 = candidates[i][2].y - candidates[i][0].y;

    if ((dx1 * dy2 - dy1 * dx2) < 0) {
      swap = candidates[i][1];
      candidates[i][1] = candidates[i][3];
      candidates[i][3] = swap;
    }
  }

  return candidates;
};

AR.Detector.prototype.notTooNear = function (candidates, minDist) {
  var notTooNear = [],
    len = candidates.length,
    dist, dx, dy, i, j, k;

  for (i = 0; i < len; ++i) {

    for (j = i + 1; j < len; ++j) {
      dist = 0;

      for (k = 0; k < 4; ++k) {
        dx = candidates[i][k].x - candidates[j][k].x;
        dy = candidates[i][k].y - candidates[j][k].y;

        dist += dx * dx + dy * dy;
      }

      if ((dist / 4) < (minDist * minDist)) {

        if (CV.perimeter(candidates[i]) < CV.perimeter(candidates[j])) {
          candidates[i].tooNear = true;
        } else {
          candidates[j].tooNear = true;
        }
      }
    }
  }

  for (i = 0; i < len; ++i) {
    if (!candidates[i].tooNear) {
      notTooNear.push(candidates[i]);
    }
  }

  return notTooNear;
};

AR.Detector.prototype.findMarkers = function (imageSrc, candidates, warpSize) {
  var markers = [],
    len = candidates.length,
    candidate, marker, i;

  for (i = 0; i < len; ++i) {
    candidate = candidates[i];

    CV.warp(imageSrc, this.homography, candidate, warpSize);

    CV.threshold(this.homography, this.homography, CV.otsu(this.homography));

    marker = this.getMarker(this.homography, candidate);
    if (marker) {
      markers.push(marker);
    }
  }

  return markers;
};

AR.Detector.prototype.getMarker = function (imageSrc, candidate) {
  var markSize = this.dictionary.markSize;
  var width = (imageSrc.width / markSize) >>> 0,
    minZero = (width * width) >> 1,
    bits = [],
    rotations = [],
    square, inc, i, j;

  for (i = 0; i < markSize; ++i) {
    inc = (0 === i || (markSize - 1) === i) ? 1 : (markSize - 1);

    for (j = 0; j < markSize; j += inc) {
      square = {
        x: j * width,
        y: i * width,
        width: width,
        height: width
      };
      if (CV.countNonZero(imageSrc, square) > minZero) {
        return null;
      }
    }
  }

  for (i = 0; i < markSize - 2; ++i) {
    bits[i] = [];

    for (j = 0; j < markSize - 2; ++j) {
      square = {
        x: (j + 1) * width,
        y: (i + 1) * width,
        width: width,
        height: width
      };

      bits[i][j] = CV.countNonZero(imageSrc, square) > minZero ? 1 : 0;
    }
  }

  rotations[0] = bits;

  var foundMin = null;
  var rot = 0;
  for (i = 0; i < 4; i++) {
    var found = this.dictionary.find(rotations[i]);
    if (found && (foundMin === null || found.distance < foundMin.distance)) {
      foundMin = found;
      rot = i;
      if (foundMin.distance === 0)
        break;
    }
    rotations[i + 1] = this.rotate(rotations[i]);
  }

  if (foundMin)
    return new AR.Marker(foundMin.id, this.rotate2(candidate, 4 - rot), foundMin.distance);

  return null;
};

AR.Detector.prototype.rotate = function (src) {
  var dst = [],
    len = src.length,
    i, j;

  for (i = 0; i < len; ++i) {
    dst[i] = [];
    for (j = 0; j < src[i].length; ++j) {
      dst[i][j] = src[src[i].length - j - 1][i];
    }
  }

  return dst;
};

AR.Detector.prototype.rotate2 = function (src, rotation) {
  var dst = [],
    len = src.length,
    i;

  for (i = 0; i < len; ++i) {
    dst[i] = src[(rotation + i) % len];
  }

  return dst;
};

}).call(scope);
(function () {
/* Copyright (C) 2013-2016, The Regents of The University of Michigan.
All rights reserved.
This software was developed in the APRIL Robotics Lab under the
direction of Edwin Olson, ebolson@umich.edu. This software may be
available under alternative licensing terms; contact the address above.
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
The views and conclusions contained in the software and documentation are those
of the authors and should not be interpreted as representing official policies,
either expressed or implied, of the Regents of The University of Michigan.
*/

//Dictionary extracted from https://github.com/AprilRobotics/apriltag-generation/blob/master/src/april/tag/Tag36h11.java

var AR = this.AR;
AR.DICTIONARIES['APRILTAG_36h11'] = {
  nBits: 36,
  tau: 11,
  codeList: [0xd5d628584,0xd97f18b49,0xdd280910e,0xe479e9c98,0xebcbca822,0xf31dab3ac,0x56a5d085,0x10652e1d4,0x22b1dfead,0x265ad0472,0x34fe91b86,0x3ff962cd5,0x43a25329a,0x474b4385f,0x4e9d243e9,0x5246149ae,0x5997f5538,0x683bb6c4c,0x6be4a7211,0x7e3158eea,0x81da494af,0x858339a74,0x8cd51a5fe,0x9f21cc2d7,0xa2cabc89c,0xadc58d9eb,0xb16e7dfb0,0xb8c05eb3a,0xd25ef139d,0xd607e1962,0xe4aba3076,0x2dde6a3da,0x43d40c678,0x5620be351,0x64c47fa65,0x686d7002a,0x6c16605ef,0x6fbf50bb4,0x8d06d39dc,0x9f53856b5,0xadf746dc9,0xbc9b084dd,0xd290aa77b,0xd9e28b305,0xe4dd5c454,0xfad2fe6f2,0x181a8151a,0x26be42c2e,0x2e10237b8,0x405cd5491,0x7742eab1c,0x85e6ac230,0x8d388cdba,0x9f853ea93,0xc41ea2445,0xcf1973594,0x14a34a333,0x31eacd15b,0x6c79d2dab,0x73cbb3935,0x89c155bd3,0x8d6a46198,0x91133675d,0xa708d89fb,0xae5ab9585,0xb9558a6d4,0xb98743ab2,0xd6cec68da,0x1506bcaef,0x4becd217a,0x4f95c273f,0x658b649dd,0xa76c4b1b7,0xecf621f56,0x1c8a56a57,0x3628e92ba,0x53706c0e2,0x5e6b3d231,0x7809cfa94,0xe97eead6f,0x5af40604a,0x7492988ad,0xed5994712,0x5eceaf9ed,0x7c1632815,0xc1a0095b4,0xe9e25d52b,0x3a6705419,0xa8333012f,0x4ce5704d0,0x508e60a95,0x877476120,0xa864e950d,0xea45cfce7,0x19da047e8,0x24d4d5937,0x6e079cc9b,0x99f2e11d7,0x33aa50429,0x499ff26c7,0x50f1d3251,0x66e7754ef,0x96ad633ce,0x9a5653993,0xaca30566c,0xc298a790a,0x8be44b65d,0xdc68f354b,0x16f7f919b,0x4dde0e826,0xd548cbd9f,0xe0439ceee,0xfd8b1fd16,0x76521bb7b,0xd92375742,0xcab16d40c,0x730c9dd72,0xad9ba39c2,0xb14493f87,0x52b15651f,0x185409cad,0x77ae2c68d,0x94f5af4b5,0xa13bad55,0x61ea437cd,0xa022399e2,0x203b163d1,0x7bba8f40e,0x95bc9442d,0x41c0b5358,0x8e9c6cc81,0xeb549670,0x9da3a0b51,0xd832a67a1,0xdcd4350bc,0x4aa05fdd2,0x60c7bb44e,0x4b358b96c,0x67299b45,0xb9c89b5fa,0x6975acaea,0x62b8f7afa,0x33567c3d7,0xbac139950,0xa5927c62a,0x5c916e6a4,0x260ecb7d5,0x29b7bbd9a,0x903205f26,0xae72270a4,0x3d2ec51a7,0x82ea55324,0x11a6f3427,0x1ca1c4576,0xa40c81aef,0xbddccd730,0xe617561e,0x969317b0f,0x67f781364,0x610912f96,0xb2549fdfc,0x6e5aaa6b,0xb6c475339,0xc56836a4d,0x844e351eb,0x4647f83b4,0x908a04f5,0x7f51034c9,0xaee537fca,0x5e92494ba,0xd445808f4,0x28d68b563,0x4d25374b,0x2bc065f65,0x96dc3ea0c,0x4b2ade817,0x7c3fd502,0xe768b5caf,0x17605cf6c,0x182741ee4,0x62846097c,0x72b5ebf80,0x263da6e13,0xfa841bcb5,0x7e45e8c69,0x653c81fa0,0x7443b5e70,0xa5234afd,0x74756f24e,0x157ebf02a,0x82ef46939,0x80d420264,0x2aeed3e98,0xb0a1dd4f8,0xb5436be13,0x7b7b4b13b,0x1ce80d6d3,0x16c08427d,0xee54462dd,0x1f7644cce,0x9c7b5cc92,0xe369138f8,0x5d5a66e91,0x485d62f49,0xe6e819e94,0xb1f340eb5,0x9d198ce2,0xd60717437,0x196b856c,0xf0a6173a5,0x12c0e1ec6,0x62b82d5cf,0xad154c067,0xce3778832,0x6b0a7b864,0x4c7686694,0x5058ff3ec,0xd5e21ea23,0x9ff4a76ee,0x9dd981019,0x1bad4d30a,0xc601896d1,0x973439b48,0x1ce7431a8,0x57a8021d6,0xf9dba96e6,0x83a2e4e7c,0x8ea585380,0xaf6c0e744,0x875b73bab,0xda34ca901,0x2ab9727ef,0xd39f21b9a,0x8a10b742f,0x5f8952dba,0xf8da71ab0,0xc25f9df96,0x6f8a5d94,0xe42e63e1a,0xb78409d1b,0x792229add,0x5acf8c455,0x2fc29a9b0,0xea486237b,0xb0c9685a0,0x1ad748a47,0x3b4712d5,0xf29216d30,0x8dad65e49,0xa2cf09dd,0xb5f174c6,0xe54f57743,0xb9cf54d78,0x4a312a88a,0x27babc962,0xb86897111,0xf2ff6c116,0x82274bd8a,0x97023505e,0x52d46edd1,0x585c1f538,0xbddd00e43,0x5590b74df,0x729404a1f,0x65320855e,0xd3d4b6956,0x7ae374f14,0x2d7a60e06,0x315cd9b5e,0xfd36b4eac,0xf1df7642b,0x55db27726,0x8f15ebc19,0x992f8c531,0x62dea2a40,0x928275cab,0x69c263cb9,0xa774cca9e,0x266b2110e,0x1b14acbb8,0x624b8a71b,0x1c539406b,0x3086d529b,0x111dd66e,0x98cd630bf,0x8b9d1ffdc,0x72b2f61e7,0x9ed9d672b,0x96cdd15f3,0x6366c2504,0x6ca9df73a,0xa066d60f0,0xe7a4b8add,0x8264647ef,0xaa195bf81,0x9a3db8244,0x14d2df6a,0xb63265b7,0x2f010de73,0x97e774986,0x248affc29,0xfb57dcd11,0xb1a7e4d9,0x4bfa2d07d,0x54e5cdf96,0x4c15c1c86,0xcd9c61166,0x499380b2a,0x540308d09,0x8b63fe66f,0xc81aeb35e,0x86fe0bd5c,0xce2480c2a,0x1ab29ee60,0x8048daa15,0xdbfeb2d39,0x567c9858c,0x2b6edc5bc,0x2078fca82,0xadacc22aa,0xb92486f49,0x51fac5964,0x691ee6420,0xf63b3e129,0x39be7e572,0xda2ce6c74,0x20cf17a5c,0xee55f9b6e,0xfb8572726,0xb2c2de548,0xcaa9bce92,0xae9182db3,0x74b6e5bd1,0x137b252af,0x51f686881,0xd672f6c02,0x654146ce4,0xf944bc825,0xe8327f809,0x76a73fd59,0xf79da4cb4,0x956f8099b,0x7b5f2655c,0xd06b114a6,0xd0697ca50,0x27c390797,0xbc61ed9b2,0xcc12dd19b,0xeb7818d2c,0x92fcecda,0x89ded4ea1,0x256a0ba34,0xb6948e627,0x1ef6b1054,0x8639294a2,0xeda3780a4,0x39ee2af1d,0xcd257edc5,0x2d9d6bc22,0x121d3b47d,0x37e23f8ad,0x119f31cf6,0x2c97f4f09,0xd502abfe0,0x10bc3ca77,0x53d7190ef,0x90c3e62a6,0x7e9ebf675,0x979ce23d1,0x27f0c98e9,0xeafb4ae59,0x7ca7fe2bd,0x1490ca8f6,0x9123387ba,0xb3bc73888,0x3ea87e325,0x4888964aa,0xa0188a6b9,0xcd383c666,0x40029a3fd,0xe1c00ac5c,0x39e6f2b6e,0xde664f622,0xe979a75e8,0x7c6b4c86c,0xfd492e071,0x8fbb35118,0x40b4a09b7,0xaf80bd6da,0x70e0b2521,0x2f5c54d93,0x3f4a118d5,0x9c1897b9,0x79776eac,0x84b00b17,0x3a95ad90e,0x28c544095,0x39d457c05,0x7a3791a78,0xbb770e22e,0x9a822bd6c,0x68a4b1fed,0xa5fd27b3b,0xc3995b79,0xd1519dff1,0x8e7eee359,0xcd3ca50b1,0xb73b8b793,0x57aca1c43,0xec2655277,0x785a2c1b3,0x75a07985a,0xa4b01eb69,0xa18a11347,0xdb1f28ca3,0x877ec3e25,0x31f6341b8,0x1363a3a4c,0x75d8b9ba,0x7ae0792a9,0xa83a21651,0x7f08f9fb5,0xd0cf73a9,0xb04dcc98e,0xf65c7b0f8,0x65ddaf69a,0x2cf9b86b3,0x14cb51e25,0xf48027b5b,0xec26ea8b,0x44bafd45c,0xb12c7c0c4,0x959fd9d82,0xc77c9725a,0x48a22d462,0x8398e8072,0xec89b05ce,0xbb682d4c9,0xe5a86d2ff,0x358f01134,0x8556ddcf6,0x67584b6e2,0x11609439f,0x8488816e,0xaaf1a2c46,0xf879898cf,0x8bbe5e2f7,0x101eee363,0x690f69377,0xf5bd93cd9,0xcea4c2bf6,0x9550be706,0x2c5b38a60,0xe72033547,0x4458b0629,0xee8d9ed41,0xd2f918d72,0x78dc39fd3,0x8212636f6,0x7450a72a7,0xc4f0cf4c6,0x367bcddcd,0xc1caf8cc6,0xa7f5b853d,0x9d536818b,0x535e021b0,0xa7eb8729e,0x422a67b49,0x929e928a6,0x48e8aefcc,0xa9897393c,0x5eb81d37e,0x1e80287b7,0x34770d903,0x2eef86728,0x59266ccb6,0x110bba61,0x1dfd284ef,0x447439d1b,0xfece0e599,0x9309f3703,0x80764d1dd,0x353f1e6a0,0x2c1c12dcc,0xc1d21b9d7,0x457ee453e,0xd66faf540,0x44831e652,0xcfd49a848,0x9312d4133,0x3f097d3ee,0x8c9ebef7a,0xa99e29e88,0xe9fab22c,0x4e748f4fb,0xecdee4288,0xabce5f1d0,0xc42f6876c,0x7ed402ea0,0xe5c4242c3,0xd5b2c31ae,0x286863be6,0x160444d94,0x5f0f5808e,0xae3d44b2a,0x9f5c5d109,0x8ad9316d7,0x3422ba064,0x2fed11d56,0xbea6e3e04,0x4b029eec,0x6deed7435,0x3718ce17c,0x55857f5e2,0x2edac7b62,0x85d6c512,0xd6ca88e0f,0x2b7e1fc69,0xa699d5c1b,0xf05ad74de,0x4cf5fb56d,0x5725e07e1,0x72f18a2de,0x1cec52609,0x48534243c,0x2523a4d69,0x35c1b80d1,0xa4d7338a7,0xdb1af012,0xe61a9475d,0x5df03f91,0x97ae260bb,0x32d627fef,0xb640f73c2,0x45a1ac9c6,0x6a2202de1,0x57d3e25f2,0x5aa9f986e,0xcc859d8a,0xe3ec6cca8,0x54e95e1ae,0x446887b06,0x7516732be,0x3817ac8f5,0x3e26d938c,0xaa81bc235,0xdf387ca1b,0xf3a3b3f2,0xb4bf69677,0xae21868ed,0x81e1d2d9d,0xa0a9ea14c,0x8eee297a9,0x4740c0559,0xe8b141837,0xac69e0a3d,0x9ed83a1e1,0x5edb55ecb,0x7340fe81,0x50dfbc6bf,0x4f583508a,0xcb1fb78bc,0x4025ced2f,0x39791ebec,0x53ee388f1,0x7d6c0bd23,0x93a995fbe,0x8a41728de,0x2fe70e053,0xab3db443a,0x1364edb05,0x47b6eeed6,0x12e71af01,0x52ff83587,0x3a1575dd8,0x3feaa3564,0xeacf78ba7,0x872b94f8,0xda8ddf9a2,0x9aa920d2b,0x1f350ed36,0x18a5e861f,0x2c35b89c3,0x3347ac48a,0x7f23e022e,0x2459068fb,0xe83be4b73]
};
}).call(scope);
export const AR = scope.AR;
