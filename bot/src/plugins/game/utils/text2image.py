from PIL import Image, ImageFont, ImageDraw
import random

class TextToImage:
  LINE_CHAR_COUNT = 30*2  # 每行最大字符数：30个中文字符(=60英文字符)
  CHAR_SIZE = 30 # 字号
  TABLE_WIDTH = 4

  # 获取这段文字的最大宽度
  def get_max_count(line):
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
              else:
                  width += 1
                  ret += c
          if width >= TextToImage.LINE_CHAR_COUNT:
              ret += '\n'
              width = 0
      if ret.endswith('\n'):
          return ret
      return ret + '\n'

  # 将文字转换成图片
  def toImage(text):
    new_text = TextToImage.line_break(text)
    font = ImageFont.truetype("/home/admin/PSL/simsun.ttf", TextToImage.CHAR_SIZE, encoding="unic")
    lines = new_text.count("\n")
    im = Image.new("L", (TextToImage.get_max_count(text)*TextToImage.CHAR_SIZE // 2, TextToImage.CHAR_SIZE*lines), "white")
    draw_table = ImageDraw.Draw(im)
    draw_table.text(xy=(0, 0), text=new_text, fill='#000000', font= font, spacing=4)
    filename = str(random.randint(1, 100)) + ".png"
    im.save("/home/admin/PSL/cqhttp/data/images/text2image/" + filename)
    return filename

# 返回一个CQ Image
def toImage(text):
  filename = TextToImage.toImage(text)
  ret = "[CQ:image,file=/text2image/" + filename + "]"
  return ret
    