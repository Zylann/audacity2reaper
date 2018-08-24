import struct
import xml.etree.ElementTree as ET
import uuid
import math
import pprint
import os


AU_SAMPLE_FORMAT_16 = 3
AU_SAMPLE_FORMAT_24 = 4
AU_SAMPLE_FORMAT_FLOAT = 6


def load_au_file(au_fpath):
	with open(au_fpath, 'rb') as f:

		# See https://github.com/audacity/audacity/blob/master/src/blockfile/SimpleBlockFile.cpp

		# wxUint32 magic;      // magic number
		# wxUint32 dataOffset; // byte offset to start of audio data
		# wxUint32 dataSize;   // data length, in bytes (optional)
		# wxUint32 encoding;   // data encoding enumeration
		# wxUint32 sampleRate; // samples per second
		# wxUint32 channels; // number of interleaved channels

		hcount = 6
		hdata = struct.unpack('I' * hcount, f.read(hcount * 4))

		result = {
			'magic': hdata[0],
			'data_offset': hdata[1],
			'data_size': hdata[2],
			'encoding': hdata[3],
			'sample_rate': hdata[4],
			'channels': hdata[5]
		}

		#print(result)

		if result['magic'] == 0x2e736e64:
			encoding = result['encoding']
		else:
			print("ERROR: Endianess needs to be swapped but I dunno what to do")
			return

		f.seek(result['data_offset'])

		ds = result['data_size']

		#if ds == 0xffffffff:
			# Size was specified as optional... read to end of file I guess?
			#ds = -1

		if encoding == AU_SAMPLE_FORMAT_16:
			sfc = 'h'
		elif encoding == AU_SAMPLE_FORMAT_24:
			print("ERROR: 24-bit samples? Dunno how to read them")
			return
		elif encoding == AU_SAMPLE_FORMAT_FLOAT:
			sfc = 'f'
		else:
			print("ERROR: I dunno this format ", encoding)
			return

		sample_data = []

		# Note: the file may be very big
		i = 0
		while i < ds:
			d = f.read(4)
			if len(d) == 0:
				break
			sample_data.append(struct.unpack(sfc, d)[0])
			i += 1

		ds = i

	result['data_size'] = ds
	result['encoding'] = encoding
	result['sample_data'] = sample_data

	return result


def write_wav_file(fpath, sample_rate, channels, bits_per_sample, sample_data):

	data_chunk_size = len(sample_data) * bits_per_sample // 8
	fmt_chunk_size = 2 + 2 + 4 + 4 + 2 + 2
	riff_chunk_size = 4 + (8 + fmt_chunk_size) + (8 + data_chunk_size)

	with open(fpath, 'wb') as f:

		f.write(b'RIFF')
		f.write(struct.pack('I', riff_chunk_size))

		f.write(b'WAVE')
		#wave_chunk_size = ???
		#f.write(struct.pack('I', wave_chunk_size))

		# ----------
		f.write(b'fmt ')
		f.write(struct.pack('I', fmt_chunk_size))

		# Format
		# PCM = 1 (i.e. Linear quantization) Values other than 1 indicate some form of compression.
		f.write(struct.pack('H', 1))

		f.write(struct.pack('H', channels))

		f.write(struct.pack('I', sample_rate))

		# SampleRate * NumChannels * BitsPerSample/8
		byte_rate = sample_rate * channels * bits_per_sample // 8
		f.write(struct.pack('I', byte_rate))

		# NumChannels * BitsPerSample/8
		block_align = channels * bits_per_sample // 8
		f.write(struct.pack('H', block_align))

		# 8 bits = 8, 16 bits = 16, etc.
		f.write(struct.pack('H', bits_per_sample))

		# ----------
		f.write(b'data')
		f.write(struct.pack('I', data_chunk_size))
		sfc = 'h'
		if bits_per_sample == 32:
			sfc = 'i'
		for v in sample_data:
			f.write(struct.pack(sfc, v))


def convert_au_to_wav(src_path, dst_path):

	au = load_au_file(src_path)

	samples = au['sample_data']

	if au['encoding'] == AU_SAMPLE_FORMAT_FLOAT:
		for i, v in enumerate(samples):
			# We want 16-bit PCM
			samples[i] = int(v * 32767.0)

	write_wav_file(dst_path, au['sample_rate'], au['channels'], 16, samples)


def load_audacity_project(fpath):
	root = ET.parse(fpath).getroot()

	rate = int(float(root.attrib["rate"]))
	name = root.attrib['projname']

	ns = { 'ns': 'http://audacity.sourceforge.net/xml/' }

	data_dir = os.path.splitext(fpath)[0] + '_data'
	if not os.path.isdir(data_dir):
		data_dir = ""

	output = {
		'rate': rate,
		'name': name,
		'data_dir': data_dir,
		'tracks': []
	}

	for project_item in root:
		tag = project_item.tag.split('}')[1]

		if tag == 'wavetrack':

			o_track = {
				'name': project_item.attrib['name'],
				'channel': project_item.attrib['channel'],
				'linked': True if project_item.attrib['linked'] == '1' else False,
				'mute': True if project_item.attrib['mute'] == '1' else False,
				'solo': True if project_item.attrib['solo'] == '1' else False,
				'rate': int(project_item.attrib['rate']),
				'gain': float(project_item.attrib['gain']),
				'pan': float(project_item.attrib['pan']),
				'color_index': int(project_item.attrib['colorindex']),
				'clips': []
			}

			output['tracks'].append(o_track)

			waveclips = project_item.findall('ns:waveclip', ns)

			for waveclip in waveclips:

				o_clip = {
					'offset': float(waveclip.attrib['offset']),
					'color_index': int(waveclip.attrib['colorindex']),
				}

				o_track['clips'].append(o_clip)

				sequence = waveclip.findall('ns:sequence', ns)[0]
				o_sequence = {
					'max_samples': int(sequence.attrib['maxsamples']),
					'sample_format': int(sequence.attrib['sampleformat']),
					'numsamples': int(sequence.attrib['numsamples']),
					'blocks': []
				}

				o_clip['sequence'] = o_sequence

				# TODO Envelopes
				envelope = waveclip.findall('ns:envelope', ns)[0]
				o_clip['envelope'] = {}

				for waveblock in sequence.findall('ns:waveblock', ns):
					# TODO I'm amazed by the seemingly unnecessary nesting of this data...
					# taking a shortcut for now until I understand why
					waveblock_start = int(waveblock.attrib['start'])

					for block in waveblock:
						btag = block.tag.split('}')[1]

						if btag == 'simpleblockfile':

							o_sequence['blocks'].append({
								'filename': block.attrib['filename'],
								'len': int(block.attrib['len']),
								'min': float(block.attrib['min']),
								'max': float(block.attrib['max']),
								'rms': float(block.attrib['rms']),
								'type': btag,
								'start': waveblock_start
							})

						# TODO Support alias blocks (file references)

	return output


def convert_au_files_from_audacity_project(project, target_dir):

	if project['data_dir'] == "":
		# No data
		return

	indexed_files = {}
	for root, dirs, files in os.walk(project['data_dir']):
		for name in files:
			indexed_files[name] = os.path.join(root, name)

	if not os.path.isdir(target_dir):
		os.makedirs(target_dir)

	for track in project['tracks']:
		for clip in track['clips']:

			sequence = clip['sequence']

			if len(sequence['blocks']) > 1:
				print("ERROR: Multi-block clips are not entirely supported yet")

			for block in sequence['blocks']:
				if block['type'] == 'simpleblockfile':
					# This is mostly because I assume this rather than knowing it
					assert block['filename'].endswith('.au')

					src_fpath = indexed_files[block['filename']]

					dst_fname = os.path.splitext(os.path.basename(src_fpath))[0] + '.wav'
					dst_fpath = os.path.join(target_dir, dst_fname)
					
					if os.path.isfile(dst_fpath):
						print("Overwriting ", dst_fpath)

					convert_au_to_wav(src_fpath, dst_fpath)

					# TODO We may want to concatenate blocks, for now we consider just one
					if 'filename' not in clip:
						clip['filename'] = dst_fpath


def write_rpp_file_from_audacity_project(fpath, project):

	audacity_color_to_peakcol = [
		0, # 0: Default color in Audacity (blue)
		0x013333ff, # 1: Red
		0x0133ff33, # 2: Green
		0x01222222 # 3: Black
	]

	def get_file_tag(fname):
		ext = os.path.splitext(fname)[1]
		if ext == '.wav':
			return 'WAVE'
		elif ext == 'ogg':
			return 'VORBIS'
		return ext[1:].upper()

	# Audacity saves gain as a linear value, and it turns out Reaper also does
	# def linear2db(p_linear)
	# 	return math.log(p_linear) * 8.6858896380650365530225783783321

	class RppWriter:
		def __init__(self, f):
			self.indent_unit = "  "
			self.indent = ""
			self.f = f

		def open_block(self, tag, *args):
			self.f.write('{0}<{1}'.format(self.indent, tag))
			self._args(args)
			self.indent += self.indent_unit

		def close_block(self):
			self.indent = self.indent[:-len(self.indent_unit)]
			self.f.write('{0}>\n'.format(self.indent))

		def line(self, tag, *args):
			self.f.write('{0}{1}'.format(self.indent, tag))
			self._args(args)

		def _args(self, args):
			for v in args:
				if type(v) == str:
					s = ' "{0}"'# if v.contains(' ') else ' {0}'
					self.f.write(s.format(v))
				elif type(v) == bool:
					self.f.write(' {0}'.format(1 if v else 0))
				elif type(v) == uuid.UUID:
					self.f.write(' {' + str(v).upper() + '}')
				else:
					self.f.write(' ' + str(v))
			self.f.write('\n')

	# One nice thing about Reaper projects is that you can omit things in it,
	# it will not complain and just load what it finds, apparently

	with open(fpath, 'w', encoding="utf-8") as f:
		w = RppWriter(f)

		# Arbitrary version, which happens to be mine at time of writing.
		# TODO I don't know what the number at the end is
		w.open_block('REAPER_PROJECT', 0.1, '5.92/x64', 1534982487)

		project_samplerate = int(project['rate'])
		w.line('SAMPLERATE', project_samplerate, 0, 0)

		for track in project['tracks']:

			track_uid = uuid.uuid4()

			w.open_block('TRACK', track_uid)

			w.line('NAME', track['name'])
			w.line('TRACKID', track_uid)
			w.line('VOLPAN', track['gain'], track['pan'], -1, -1, 1)
			w.line('NCHAN', 2)
			w.line('MUTESOLO', track['mute'], track['solo'])
			w.line('PEAKCOL', audacity_color_to_peakcol[track['color_index']])

			for clip in track['clips']:

				w.open_block('ITEM')

				w.line('POSITION', clip['offset'])
				# TODO I don't know what these UIDs are
				w.line('IGUID', uuid.uuid4())
				w.line('GUID', uuid.uuid4())
				# TODO Take name from audio file
				w.line('NAME', "")

				nsamples = clip['sequence']['numsamples']
				item_len_seconds = nsamples / project_samplerate

				w.line('LENGTH', item_len_seconds)
				
				w.open_block('SOURCE ' + get_file_tag(clip['filename']))
				# Note: the filename at clip-level is obtained at an earlier conversion stage,
				# because usually Audacity stores audio as blocks which are later concatenated.
				# Reaper doesn't need this, so it's handy to take care of that before.
				w.line('FILE', clip['filename'])
				w.close_block()

				# Note: sources like this can exist:
				# <SOURCE SECTION
				#   LENGTH 3.55565072008221
				#   STARTPOS 7.40378238649376
				#   OVERLAP 0.01
				#   <SOURCE FLAC
				#     FILE "D:\PROJETS\AUDIO\coproductions\1287\Episodes\Episode 7\foule_armee.flac"
				#   >
				# >

				w.close_block()

			w.close_block()

		w.close_block()


def main():

	project = load_audacity_project("project.aup")
	#pp = pprint.PrettyPrinter(indent=4)
	#pp.pprint(project)

	convert_au_files_from_audacity_project(project, "WaveData")

	write_rpp_file_from_audacity_project("project.rpp", project)

main()


