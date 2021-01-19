create table IF NOT EXISTS `schedule` (
  `ID` int(11) NOT NULL,
  `Round` int(11) NOT NULL,
  `Home` bigint NOT NULL,
  `Away` bigint NOT NULL,
  `Finished` boolean default False,
  `Home_Goal` int(11) default 0,
  `Away_Goal` int(11) default 0,
  primary key(`id`)
) default charset = utf8;