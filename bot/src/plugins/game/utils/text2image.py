from game.config import *
from game.utils.const import *
from PIL import Image, ImageFont, ImageDraw
import os
import random

os.makedirs(PROJECT_DIR + "/cqhttp/data/images/text2image/", exist_ok=True)

class TextToImage:
  LINE_CHAR_COUNT = 30*2  # 每行最大字符数：30个中文字符(=60英文字符)
  CHAR_SIZE = 20 # 字号
  TABLE_WIDTH = 4

  # 计算一段文字的最大宽度
  def get_max_width(line):
    ret = 0
    width = 0
    for c in line:
      if (width >= TextToImage.LINE_CHAR_COUNT):
          return TextToImage.LINE_CHAR_COUNT
      if len(c.encode('utf8')) == 3:
          width += 2
      else:
          if c == '\t':
              width += TextToImage.TABLE_WIDTH - width % TextToImage.TABLE_WIDTH
          elif c == '\n':
              ret = max(ret, width)
              width = 0
          elif c == '/' or c == '~':
              continue
          else:
              width += 1
    ret = max(ret, min(width, TextToImage.LINE_CHAR_COUNT))
    return ret

  # 自动换行
  def line_break(line):
      ret = ''
      width = 0
      for c in line:
          if len(c.encode('utf8')) == 3:  # 中文
              if TextToImage.LINE_CHAR_COUNT == width + 1:  # 剩余位置不够一个汉字
                  width = 2
                  ret += '\n' + c
              else: # 中文宽度加2，注意换行边界
                  width += 2
                  ret += c
          else:
              if c == '\t':
                  space_c = TextToImage.TABLE_WIDTH - width % TextToImage.TABLE_WIDTH  # 已有长度对TABLE_WIDTH取余
                  ret += ' ' * space_c
                  width += space_c
              elif c == '\n':
                  width = 0
                  ret += c
              elif c == '/' or c == '~':
                  ret += c
              else:
                  width += 1
                  ret += c
          if width >= TextToImage.LINE_CHAR_COUNT:
              ret += '\n'
              width = 0
      if ret.endswith('\n'):
          return ret
      return ret + '\n'

  # 计算一行文字的宽度
  def get_width(text):
    width = 0
    for c in text:
      if len(c.encode('utf8')) == 3:
        width += 2
      else:
        if c == '\t':
          width += TextToImage.TABLE_WIDTH - width % TextToImage.TABLE_WIDTH
        elif c == '\n':
          continue
        elif c == '/' or c == '~':
          continue
        else:
          width += 1
    return width


  # 将文字转换成图片
  def toImage(text):
    new_text = TextToImage.line_break(text)
    font = ImageFont.truetype(PROJECT_DIR + "/sarasa.ttf", TextToImage.CHAR_SIZE, encoding="unic")
    lines = new_text.count("\n")
    im = Image.new("RGB", (TextToImage.get_max_width(text)*TextToImage.CHAR_SIZE // 2, (TextToImage.CHAR_SIZE+2)*lines), "white")

    draw_table = ImageDraw.Draw(im)
    lines = new_text.split("\n")
    for i, line in enumerate(lines):
      items = line.split("/")
      offset = 0
      for j, item in enumerate(items):
        if item == "":
          continue 
        if item[0] == '~':
          color = Const.COLOR[item[1]]
          item = item[2:]
        else:
          color = "black"
        draw_table.text(xy=(offset, (TextToImage.CHAR_SIZE+2)*i), text=item, fill=color, font= font)

        offset += TextToImage.get_width(item)*TextToImage.CHAR_SIZE//2

    filename = str(random.randint(1, 100)) + ".png"
    im.save(PROJECT_DIR + "/cqhttp/data/images/text2image/" + filename)
    return filename

# 返回一个CQ Image
def toImage(text):
  if not PICTURE_MODE:
    return text
  filename = TextToImage.toImage(text)
  ret = "[CQ:image,file=/text2image/" + filename + "]"
  return ret
    