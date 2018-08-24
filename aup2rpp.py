import struct
import xml.etree.ElementTree as ET
import uuid
import math
import pprint


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

		print(result)

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


def load_audacity_project(fpath):
	root = ET.parse(fpath).getroot()

	rate = int(float(root.attrib["rate"]))
	name = root.attrib['projname']

	ns = { 'ns': 'http://audacity.sourceforge.net/xml/' }

	output = {
		'rate': rate,
		'name': name,
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
								'start': waveblock_start
							})

	return output


# Audacity saves gain as a linear value, and it turns out Reaper also does
# def linear2db(p_linear)
# 	return math.log(p_linear) * 8.6858896380650365530225783783321


def write_rpp_file_from_audacity_project(fpath, project):
	# One nice thing about Reaper projects is that you can omit things in it,
	# it will not complain and just load what it finds, apparently

	indent_unit = "  "

	def b2i(b):
		return 1 if b else 0

	def audacity_color_to_peakcol(c):
		if c == 0: # Default color in Audacity (blue)
			return 0
		if c == 1: # Red
			return 0x013333ff
		if c == 2: # Green
			return 0x0133ff33
		if c == 3: # Black
			return 0x01222222

	def generate_uid():
		return '{' + str(uuid.uuid4()).upper() + '}'

	with open(fpath, 'w', encoding="utf-8") as f:
		f.write('<REAPER_PROJECT 0.1 \"5.92/x64\" 1534982487\n')
		indent = indent_unit

		project_samplerate = int(project['rate'])
		f.write('{0}SAMPLERATE {1} 0 0\n'.format(indent, project_samplerate))

		for track in project['tracks']:

			track_uid = generate_uid()

			f.write('{0}<TRACK {1}\n'.format(indent, track_uid))
			indent += indent_unit

			f.write('{0}NAME "{1}"\n'.format(indent, track['name']))
			f.write('{0}TRACKID {1}\n'.format(indent, track_uid))
			f.write('{0}VOLPAN {1} {2} -1 -1 1\n'.format(indent, track['gain'], track['pan']))
			f.write('{0}NCHAN {1}\n'.format(indent, track['channel']))
			f.write('{0}MUTESOLO {1} {2} 0\n'.format(indent, b2i(track['mute']), b2i(track['solo'])))
			f.write('{0}PEAKCOL {1}\n'.format(indent, audacity_color_to_peakcol(track['color_index'])))

			for clip in track['clips']:
				f.write('{0}<ITEM\n'.format(indent))
				indent += indent_unit

				f.write('{0}POSITION {1}\n'.format(indent, clip['offset']))
				f.write('{0}IGUID {1}\n'.format(indent, generate_uid()))
				f.write('{0}GUID {1}\n'.format(indent, generate_uid()))
				# TODO Take name from audio file
				f.write('{0}NAME "{1}"\n'.format(indent, ""))

				nsamples = clip['sequence']['numsamples']
				item_len_seconds = nsamples / project_samplerate
				f.write('{0}LENGTH "{1}"\n'.format(indent, item_len_seconds))

				# TODO Actually implement source
				f.write('{0}<SOURCE WAV\n'.format(indent))
				f.write('{0}{1}FILE "{2}"\n'.format(indent, indent_unit, "todo.wav"))
				f.write(indent)
				f.write('>\n')

				indent = indent[:-len(indent_unit)]

				f.write(indent)
				f.write('>\n')

			indent = indent[:-len(indent_unit)]

			f.write(indent)
			f.write('>\n')

		f.write('>')


def test_convert_au_to_wav():

	print("Loading AU file")
	au = load_au_file("project_data/e08/d08/e0808cd2.au")

	samples = au['sample_data']

	if au['encoding'] == AU_SAMPLE_FORMAT_FLOAT:
		print("Converting data")
		for i, v in enumerate(samples):
			# We want 16-bit PCM
			samples[i] = int(v * 32767.0)

	print("Saving WAV file")
	write_wav_file("output.wav", au['sample_rate'], au['channels'], 16, samples)

	print("Done")


def main():

	project = load_audacity_project("project.aup")
	# pp = pprint.PrettyPrinter(indent=4)
	# pp.pprint(project)
	write_rpp_file_from_audacity_project("project.rpp", project)

main()


